"""
Audio debug and instrumentation module.

Tracks audio playback statistics for diagnostics and debugging.
Enable with DJE_AUDIO_DEBUG=true in .env for verbose logging.
"""

import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from collections import deque


@dataclass
class AudioStats:
    """Statistics for audio playback diagnostics."""
    tracks_played: int = 0
    tracks_failed: int = 0
    ffmpeg_retries: int = 0
    download_times: deque = field(default_factory=lambda: deque(maxlen=50))
    resolve_times: deque = field(default_factory=lambda: deque(maxlen=50))
    playback_errors: deque = field(default_factory=lambda: deque(maxlen=20))
    last_playback_start: Optional[float] = None


# Global stats instance
_stats = AudioStats()


def is_debug_enabled() -> bool:
    """Check if audio debug mode is enabled."""
    from . import config
    return getattr(config, 'DJE_AUDIO_DEBUG', False)


def log_download_time(duration_seconds: float) -> None:
    """Record a download time for statistics."""
    _stats.download_times.append(duration_seconds)


def log_resolve_time(duration_seconds: float) -> None:
    """Record a YouTube resolve time for statistics."""
    _stats.resolve_times.append(duration_seconds)


def log_playback_start() -> None:
    """Record a successful playback start."""
    _stats.tracks_played += 1
    _stats.last_playback_start = time.time()


def log_playback_error(error_type: str, message: str) -> None:
    """Record a playback error."""
    _stats.tracks_failed += 1
    _stats.playback_errors.append({
        'time': time.time(),
        'type': error_type,
        'message': message[:200]  # Truncate long messages
    })


def log_ffmpeg_retry() -> None:
    """Record an FFmpeg retry attempt."""
    _stats.ffmpeg_retries += 1


def get_stats() -> Dict:
    """Get current audio statistics as a dictionary."""
    # Calculate averages
    avg_download = 0.0
    if _stats.download_times:
        avg_download = sum(_stats.download_times) / len(_stats.download_times)

    avg_resolve = 0.0
    if _stats.resolve_times:
        avg_resolve = sum(_stats.resolve_times) / len(_stats.resolve_times)

    # Get recent errors by type
    error_counts: Dict[str, int] = {}
    recent_cutoff = time.time() - 300  # Last 5 minutes
    for error in _stats.playback_errors:
        if error['time'] > recent_cutoff:
            error_type = error['type']
            error_counts[error_type] = error_counts.get(error_type, 0) + 1

    return {
        'tracks_played': _stats.tracks_played,
        'tracks_failed': _stats.tracks_failed,
        'ffmpeg_retries': _stats.ffmpeg_retries,
        'avg_download_time': round(avg_download, 2),
        'avg_resolve_time': round(avg_resolve, 2),
        'recent_errors_by_type': error_counts,
        'debug_enabled': is_debug_enabled(),
        'last_playback_start': _stats.last_playback_start,
    }


def reset_stats() -> None:
    """Reset all statistics. Useful for testing."""
    global _stats
    _stats = AudioStats()
