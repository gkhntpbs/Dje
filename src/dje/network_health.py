"""
Network health monitoring and resilience layer for Discord bot.

Provides circuit breaker pattern, exponential backoff, and network state tracking
to handle unstable VPN/WARP connections gracefully.
"""

import asyncio
import logging
import random
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class NetworkState(Enum):
    """Current network health state."""
    OK = "ok"
    DEGRADED = "degraded"
    OFFLINE = "offline"


@dataclass
class NetworkFailure:
    """Record of a network failure."""
    timestamp: float
    error_type: str
    message: str


@dataclass
class NetworkHealthStats:
    """Current network health statistics."""
    state: NetworkState = NetworkState.OK
    consecutive_failures: int = 0
    total_failures: int = 0
    last_success_time: Optional[float] = None
    last_failure_time: Optional[float] = None
    last_failure_message: Optional[str] = None
    recent_failures: deque = field(default_factory=lambda: deque(maxlen=50))
    gateway_connect_time: Optional[float] = None
    event_loop_lag_detected: bool = False


class NetworkHealth:
    """
    Central network health monitor with circuit breaker pattern.

    Features:
    - Tracks consecutive and total network failures
    - Implements exponential backoff with jitter
    - Circuit breaker state management (OK -> DEGRADED -> OFFLINE)
    - Provides diagnostics and recommendations for WARP/VPN issues
    """

    def __init__(
        self,
        backoff_base_sec: float = 2.0,
        backoff_max_sec: float = 300.0,
        fail_window_sec: float = 120.0,
        fail_threshold: int = 5,
    ):
        """
        Initialize network health monitor.

        Args:
            backoff_base_sec: Base delay for exponential backoff
            backoff_max_sec: Maximum backoff delay
            fail_window_sec: Time window to count failures for circuit breaker
            fail_threshold: Number of failures in window to trigger OFFLINE state
        """
        self.backoff_base_sec = backoff_base_sec
        self.backoff_max_sec = backoff_max_sec
        self.fail_window_sec = fail_window_sec
        self.fail_threshold = fail_threshold

        self._stats = NetworkHealthStats()
        self._lock = asyncio.Lock()

    async def record_success(self) -> None:
        """Record a successful network operation."""
        async with self._lock:
            current_time = time.time()
            self._stats.last_success_time = current_time

            # Reset consecutive failures on success
            if self._stats.consecutive_failures > 0:
                logger.info(
                    "Network recovered after %d consecutive failures",
                    self._stats.consecutive_failures
                )
                self._stats.consecutive_failures = 0

            # Transition to OK state if we were degraded
            if self._stats.state != NetworkState.OK:
                old_state = self._stats.state
                self._stats.state = NetworkState.OK
                logger.info("Network state transition: %s -> OK", old_state.value)

    async def record_failure(
        self,
        error: Exception,
        error_type: str = "unknown"
    ) -> None:
        """
        Record a network failure and update state.

        Args:
            error: The exception that occurred
            error_type: Type of error (dns, gateway, http, etc.)
        """
        async with self._lock:
            current_time = time.time()
            error_message = str(error)

            self._stats.consecutive_failures += 1
            self._stats.total_failures += 1
            self._stats.last_failure_time = current_time
            self._stats.last_failure_message = error_message

            # Add to recent failures deque
            failure = NetworkFailure(
                timestamp=current_time,
                error_type=error_type,
                message=error_message
            )
            self._stats.recent_failures.append(failure)

            # Count failures within the time window
            cutoff_time = current_time - self.fail_window_sec
            recent_count = sum(
                1 for f in self._stats.recent_failures
                if f.timestamp >= cutoff_time
            )

            # Update state based on failure count
            old_state = self._stats.state
            if recent_count >= self.fail_threshold:
                self._stats.state = NetworkState.OFFLINE
            elif self._stats.consecutive_failures >= 2:
                self._stats.state = NetworkState.DEGRADED

            if old_state != self._stats.state:
                logger.warning(
                    "Network state transition: %s -> %s (failures: %d consecutive, %d in %ds window)",
                    old_state.value,
                    self._stats.state.value,
                    self._stats.consecutive_failures,
                    recent_count,
                    int(self.fail_window_sec)
                )

            # Log the specific failure
            logger.error(
                "Network failure #%d (consecutive: %d, type: %s): %s",
                self._stats.total_failures,
                self._stats.consecutive_failures,
                error_type,
                error_message
            )

    async def record_gateway_connect(self) -> None:
        """Record successful Discord gateway connection."""
        async with self._lock:
            self._stats.gateway_connect_time = time.time()
            logger.info("Discord gateway connected")

    async def record_event_loop_lag(self) -> None:
        """Record that event loop lag has been detected."""
        async with self._lock:
            if not self._stats.event_loop_lag_detected:
                self._stats.event_loop_lag_detected = True
                logger.warning(
                    "Event loop lag detected - heartbeat may be delayed. "
                    "Check for blocking operations."
                )

    async def get_stats(self) -> NetworkHealthStats:
        """Get current network health statistics."""
        async with self._lock:
            # Return a copy to avoid race conditions
            return NetworkHealthStats(
                state=self._stats.state,
                consecutive_failures=self._stats.consecutive_failures,
                total_failures=self._stats.total_failures,
                last_success_time=self._stats.last_success_time,
                last_failure_time=self._stats.last_failure_time,
                last_failure_message=self._stats.last_failure_message,
                recent_failures=self._stats.recent_failures.copy(),
                gateway_connect_time=self._stats.gateway_connect_time,
                event_loop_lag_detected=self._stats.event_loop_lag_detected,
            )

    async def is_healthy(self) -> bool:
        """Check if network is healthy (OK state)."""
        async with self._lock:
            return self._stats.state == NetworkState.OK

    async def should_backoff(self) -> bool:
        """Check if operations should back off due to network issues."""
        async with self._lock:
            return self._stats.state in (NetworkState.DEGRADED, NetworkState.OFFLINE)

    async def should_circuit_break(self) -> bool:
        """Check if circuit breaker should prevent operations."""
        async with self._lock:
            return self._stats.state == NetworkState.OFFLINE

    async def get_backoff_delay(self) -> float:
        """
        Calculate exponential backoff delay with jitter.

        Returns:
            Delay in seconds, or 0 if network is healthy
        """
        async with self._lock:
            if self._stats.state == NetworkState.OK:
                return 0.0

            # Exponential backoff: base * 2^(consecutive_failures - 1)
            exponent = min(self._stats.consecutive_failures - 1, 10)  # Cap exponent
            delay = self.backoff_base_sec * (2 ** exponent)

            # Cap at maximum
            delay = min(delay, self.backoff_max_sec)

            # Add jitter (±25%)
            jitter = delay * 0.25 * (random.random() * 2 - 1)
            delay = delay + jitter

            return max(0.0, delay)

    def get_diagnostics(self) -> dict:
        """
        Get diagnostic information for troubleshooting.

        Returns synchronously for use in exception handlers.
        """
        stats = self._stats
        current_time = time.time()

        diagnostics = {
            "state": stats.state.value,
            "consecutive_failures": stats.consecutive_failures,
            "total_failures": stats.total_failures,
        }

        if stats.last_success_time:
            elapsed = current_time - stats.last_success_time
            diagnostics["seconds_since_success"] = int(elapsed)

        if stats.last_failure_time:
            elapsed = current_time - stats.last_failure_time
            diagnostics["seconds_since_failure"] = int(elapsed)
            diagnostics["last_failure"] = stats.last_failure_message

        if stats.gateway_connect_time:
            elapsed = current_time - stats.gateway_connect_time
            diagnostics["seconds_since_gateway_connect"] = int(elapsed)

        diagnostics["event_loop_lag"] = stats.event_loop_lag_detected

        # Count recent failures by type
        cutoff = current_time - self.fail_window_sec
        recent = [f for f in stats.recent_failures if f.timestamp >= cutoff]
        if recent:
            failure_types = {}
            for f in recent:
                failure_types[f.error_type] = failure_types.get(f.error_type, 0) + 1
            diagnostics["recent_failure_types"] = failure_types

        return diagnostics


def calculate_backoff(
    attempt: int,
    base_sec: float = 2.0,
    max_sec: float = 300.0,
    jitter: bool = True
) -> float:
    """
    Pure function to calculate exponential backoff delay.

    Args:
        attempt: Attempt number (1-indexed)
        base_sec: Base delay in seconds
        max_sec: Maximum delay in seconds
        jitter: Whether to add random jitter

    Returns:
        Delay in seconds
    """
    if attempt <= 0:
        return 0.0

    exponent = min(attempt - 1, 10)
    delay = base_sec * (2 ** exponent)
    delay = min(delay, max_sec)

    if jitter:
        jitter_amount = delay * 0.25 * (random.random() * 2 - 1)
        delay = delay + jitter_amount

    return max(0.0, delay)


def is_dns_error(error: Exception) -> bool:
    """Check if error is a DNS resolution failure."""
    error_str = str(error).lower()
    error_type = type(error).__name__.lower()

    dns_indicators = [
        "clientconnectordnserror",
        "dns",
        "nodename nor servname",
        "name or service not known",
        "temporary failure in name resolution",
        "getaddrinfo failed",
    ]

    return any(indicator in error_str or indicator in error_type
               for indicator in dns_indicators)


def is_gateway_error(error: Exception) -> bool:
    """Check if error is a Discord gateway connection failure."""
    error_str = str(error).lower()
    error_type = type(error).__name__.lower()

    gateway_indicators = [
        "gateway",
        "websocket",
        "session",
        "invalidat",
        "can't keep up",
        "heartbeat",
        "connectionclosed",
    ]

    return any(indicator in error_str or indicator in error_type
               for indicator in gateway_indicators)


def get_warp_troubleshooting_tips() -> list[str]:
    """Get troubleshooting tips for Cloudflare WARP/VPN issues."""
    return [
        "✓ Ensure WARP is connected and stable",
        "✓ Try switching WARP mode (WARP vs WARP+)",
        "✓ Check if Discord domain is excluded in split-tunnel settings",
        "✓ Use a stable DNS resolver (1.1.1.1 or 8.8.8.8)",
        "✓ Restart WARP application if issues persist",
        "✓ Disable Wi-Fi power saving/sleep on your router",
        "✓ Use ethernet connection if possible",
        "✓ Consider running bot on a stable VPS/server",
    ]
