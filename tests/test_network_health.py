"""
Unit tests for network_health module.
"""

import asyncio
import time
import pytest
from src.dje import network_health


class TestBackoffCalculation:
    """Test pure backoff calculation function."""

    def test_backoff_zero_attempts(self):
        """Backoff for 0 attempts should be 0."""
        delay = network_health.calculate_backoff(0, base_sec=2.0, max_sec=300.0, jitter=False)
        assert delay == 0.0

    def test_backoff_first_attempt(self):
        """First attempt should use base delay."""
        delay = network_health.calculate_backoff(1, base_sec=2.0, max_sec=300.0, jitter=False)
        assert delay == 2.0

    def test_backoff_exponential_growth(self):
        """Backoff should grow exponentially."""
        delays = [
            network_health.calculate_backoff(i, base_sec=2.0, max_sec=300.0, jitter=False)
            for i in range(1, 6)
        ]
        # Should be: 2, 4, 8, 16, 32
        assert delays == [2.0, 4.0, 8.0, 16.0, 32.0]

    def test_backoff_caps_at_max(self):
        """Backoff should not exceed max delay."""
        delay = network_health.calculate_backoff(100, base_sec=2.0, max_sec=60.0, jitter=False)
        assert delay == 60.0

    def test_backoff_with_jitter(self):
        """Backoff with jitter should vary slightly."""
        delays = [
            network_health.calculate_backoff(3, base_sec=2.0, max_sec=300.0, jitter=True)
            for _ in range(10)
        ]
        # Base delay for attempt 3 is 8.0, jitter is ±25%
        for delay in delays:
            assert 6.0 <= delay <= 10.0


class TestErrorDetection:
    """Test error type detection functions."""

    def test_is_dns_error_with_dns_exception(self):
        """Should detect DNS errors from exception message."""
        error = Exception("ClientConnectorDNSError: Cannot connect to host")
        assert network_health.is_dns_error(error)

    def test_is_dns_error_with_nodename(self):
        """Should detect nodename errors."""
        error = Exception("nodename nor servname provided, or not known")
        assert network_health.is_dns_error(error)

    def test_is_dns_error_with_normal_exception(self):
        """Should not detect non-DNS errors."""
        error = Exception("Connection timeout")
        assert not network_health.is_dns_error(error)

    def test_is_gateway_error_with_websocket(self):
        """Should detect gateway/websocket errors."""
        error = Exception("websocket connection closed")
        assert network_health.is_gateway_error(error)

    def test_is_gateway_error_with_heartbeat(self):
        """Should detect heartbeat errors."""
        error = Exception("Can't keep up, heartbeat delayed")
        assert network_health.is_gateway_error(error)

    def test_is_gateway_error_with_normal_exception(self):
        """Should not detect non-gateway errors."""
        error = Exception("File not found")
        assert not network_health.is_gateway_error(error)


class TestWARPTroubleshooting:
    """Test WARP troubleshooting tips."""

    def test_get_warp_tips_returns_list(self):
        """Should return a non-empty list of tips."""
        tips = network_health.get_warp_troubleshooting_tips()
        assert isinstance(tips, list)
        assert len(tips) > 0

    def test_get_warp_tips_format(self):
        """Tips should start with checkmark."""
        tips = network_health.get_warp_troubleshooting_tips()
        for tip in tips:
            assert isinstance(tip, str)
            assert tip.startswith("✓")


@pytest.mark.asyncio
class TestNetworkHealth:
    """Test NetworkHealth class."""

    async def test_initial_state_is_ok(self):
        """New NetworkHealth instance should start in OK state."""
        health = network_health.NetworkHealth()
        stats = await health.get_stats()
        assert stats.state == network_health.NetworkState.OK
        assert stats.consecutive_failures == 0
        assert stats.total_failures == 0

    async def test_record_success_resets_consecutive_failures(self):
        """Recording success should reset consecutive failures."""
        health = network_health.NetworkHealth()

        # Simulate some failures
        await health.record_failure(Exception("test error"), "test")
        await health.record_failure(Exception("test error"), "test")

        stats = await health.get_stats()
        assert stats.consecutive_failures == 2

        # Record success
        await health.record_success()

        stats = await health.get_stats()
        assert stats.consecutive_failures == 0
        assert stats.state == network_health.NetworkState.OK
        assert stats.last_success_time is not None

    async def test_record_failure_increments_counters(self):
        """Recording failure should increment both counters."""
        health = network_health.NetworkHealth()

        await health.record_failure(Exception("test error"), "test")

        stats = await health.get_stats()
        assert stats.consecutive_failures == 1
        assert stats.total_failures == 1
        assert stats.last_failure_time is not None
        assert stats.last_failure_message == "test error"

    async def test_state_transitions_to_degraded(self):
        """After 2 consecutive failures, state should be DEGRADED."""
        health = network_health.NetworkHealth()

        await health.record_failure(Exception("error 1"), "test")
        await health.record_failure(Exception("error 2"), "test")

        stats = await health.get_stats()
        assert stats.state == network_health.NetworkState.DEGRADED

    async def test_state_transitions_to_offline(self):
        """After threshold failures in window, state should be OFFLINE."""
        health = network_health.NetworkHealth(
            fail_threshold=3,
            fail_window_sec=10.0
        )

        # Record 3 failures in quick succession
        for i in range(3):
            await health.record_failure(Exception(f"error {i}"), "test")

        stats = await health.get_stats()
        assert stats.state == network_health.NetworkState.OFFLINE

    async def test_recent_failures_tracking(self):
        """Should track recent failures in deque."""
        health = network_health.NetworkHealth()

        for i in range(5):
            await health.record_failure(Exception(f"error {i}"), f"type_{i % 2}")

        stats = await health.get_stats()
        assert len(stats.recent_failures) == 5

    async def test_is_healthy_checks_state(self):
        """is_healthy should return True only for OK state."""
        health = network_health.NetworkHealth()

        assert await health.is_healthy()

        await health.record_failure(Exception("error"), "test")
        await health.record_failure(Exception("error"), "test")

        assert not await health.is_healthy()

    async def test_should_backoff_in_degraded_state(self):
        """should_backoff should return True in DEGRADED or OFFLINE."""
        health = network_health.NetworkHealth()

        assert not await health.should_backoff()

        await health.record_failure(Exception("error"), "test")
        await health.record_failure(Exception("error"), "test")

        assert await health.should_backoff()

    async def test_should_circuit_break_only_offline(self):
        """Circuit breaker should only trigger in OFFLINE state."""
        health = network_health.NetworkHealth(fail_threshold=3, fail_window_sec=10.0)

        # DEGRADED state (2 failures)
        await health.record_failure(Exception("error"), "test")
        await health.record_failure(Exception("error"), "test")
        assert not await health.should_circuit_break()

        # OFFLINE state (3rd failure)
        await health.record_failure(Exception("error"), "test")
        assert await health.should_circuit_break()

    async def test_get_backoff_delay_returns_zero_when_healthy(self):
        """Backoff delay should be 0 when network is OK."""
        health = network_health.NetworkHealth()
        delay = await health.get_backoff_delay()
        assert delay == 0.0

    async def test_get_backoff_delay_increases_with_failures(self):
        """Backoff delay should increase with consecutive failures."""
        health = network_health.NetworkHealth(backoff_base_sec=2.0)

        delays = []
        for i in range(5):
            await health.record_failure(Exception(f"error {i}"), "test")
            delay = await health.get_backoff_delay()
            delays.append(delay)

        # Each delay should be >= 0
        assert all(d >= 0 for d in delays)
        # First failure: state is still OK (needs 2 for DEGRADED), so backoff is 0
        assert delays[0] == 0.0
        # After 2nd failure: DEGRADED state, consecutive=2, exponent=(2-1)=1, delay=2^1=4
        # Base delays: 4, 8, 16, 32 with ±25% jitter
        assert 3.0 <= delays[1] <= 5.0  # 4.0 ± 25%
        assert 6.0 <= delays[2] <= 10.0  # 8.0 ± 25%
        assert 12.0 <= delays[3] <= 20.0  # 16.0 ± 25%
        assert 24.0 <= delays[4] <= 40.0  # 32.0 ± 25%

    async def test_record_gateway_connect(self):
        """Should record gateway connection time."""
        health = network_health.NetworkHealth()

        await health.record_gateway_connect()

        stats = await health.get_stats()
        assert stats.gateway_connect_time is not None

    async def test_record_event_loop_lag(self):
        """Should record event loop lag detection."""
        health = network_health.NetworkHealth()

        assert not (await health.get_stats()).event_loop_lag_detected

        await health.record_event_loop_lag()

        stats = await health.get_stats()
        assert stats.event_loop_lag_detected

    async def test_get_diagnostics(self):
        """Should return diagnostic information."""
        health = network_health.NetworkHealth()

        await health.record_failure(Exception("test error"), "dns")
        await health.record_gateway_connect()

        diagnostics = health.get_diagnostics()

        assert "state" in diagnostics
        assert "consecutive_failures" in diagnostics
        assert "total_failures" in diagnostics
        assert diagnostics["consecutive_failures"] == 1
        assert diagnostics["total_failures"] == 1

    async def test_failure_window_excludes_old_failures(self):
        """Failures outside time window should not trigger OFFLINE."""
        health = network_health.NetworkHealth(
            fail_threshold=3,
            fail_window_sec=1.0  # Very short window
        )

        # Record 2 failures
        await health.record_failure(Exception("error 1"), "test")
        await health.record_failure(Exception("error 2"), "test")

        # Wait for window to expire
        await asyncio.sleep(1.1)

        # Record 1 more failure (should not trigger OFFLINE since old ones expired)
        await health.record_failure(Exception("error 3"), "test")

        stats = await health.get_stats()
        # Should be DEGRADED (consecutive=3) but not OFFLINE (only 1 in window)
        assert stats.state == network_health.NetworkState.DEGRADED


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
