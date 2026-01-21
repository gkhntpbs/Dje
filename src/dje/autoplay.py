"""
Autoplay module for fetching similar track recommendations.
Uses YouTube Mix/Radio playlists for recommendations.

Note: Spotify Recommendations API was deprecated in late 2024.
This module now relies on YouTube's recommendation system.
"""
import asyncio
import logging
import re
import random
from collections import deque
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from .tracks import Track
from . import youtube

logger = logging.getLogger(__name__)


class AutoplayError(Exception):
    """Base exception for autoplay errors."""
    pass


class AutoplayNotConfiguredError(AutoplayError):
    """Raised when autoplay cannot function due to missing configuration."""
    pass


@dataclass
class PlayedTrackInfo:
    """Information about a played track for recommendation seeding."""
    title: str
    artist: str
    youtube_video_id: Optional[str] = None
    spotify_track_id: Optional[str] = None
    spotify_artist_id: Optional[str] = None


class AutoplayManager:
    """Manages autoplay recommendations for a single guild."""

    def __init__(self, guild_id: int) -> None:
        self.guild_id = guild_id
        self.recent_tracks: deque[PlayedTrackInfo] = deque(maxlen=10)
        self.recommended_ids: Set[str] = set()
        self._last_seed_index: int = 0  # For rotating through seeds

    async def record_played_track(self, track: Track) -> None:
        """
        Record a played track for autoplay recommendations.
        Extracts YouTube video ID from the track URL.
        """
        if not track:
            return

        try:
            # Extract video ID from the track's webpage URL
            video_id = _extract_video_id(track.webpage_url)

            # Clean the title to extract artist info if possible
            title = track.title
            artist = ""

            # Try to extract artist from common title formats like "Artist - Song"
            if " - " in title:
                parts = title.split(" - ", 1)
                artist = parts[0].strip()
                title = parts[1].strip()

            track_info = PlayedTrackInfo(
                title=title,
                artist=artist,
                youtube_video_id=video_id,
                spotify_track_id=None,
                spotify_artist_id=None
            )

            self.recent_tracks.append(track_info)
            logger.debug(
                "Recorded track for autoplay: %s (video_id=%s)",
                track.title,
                video_id
            )
        except Exception as e:
            logger.warning("Failed to record track for autoplay: %s", e)

    async def get_recommendations(
        self, requested_by: str, count: int = 3
    ) -> List[Track]:
        """
        Get autoplay recommendations based on recent playback history.
        Uses YouTube Mix/Radio playlists with improved variety.
        """
        if not self.recent_tracks:
            logger.debug("No recent tracks for autoplay recommendations")
            return []

        # Try multiple strategies for better variety
        tracks: List[Track] = []

        # Strategy 1: YouTube Mix from recent tracks (with rotation)
        tracks = await self._get_youtube_mix_with_rotation(requested_by, count)
        if tracks:
            return tracks

        # Strategy 2: Search-based fallback (artist radio, similar songs)
        tracks = await self._get_search_based_recommendations(requested_by, count)
        if tracks:
            return tracks

        logger.warning("No autoplay recommendations found after trying all strategies")
        return []

    async def _get_youtube_mix_with_rotation(
        self, requested_by: str, count: int
    ) -> List[Track]:
        """
        Get tracks from YouTube Mix with seed rotation for variety.
        Tries multiple recent tracks as seeds to avoid repetition.
        """
        # Get list of tracks with video IDs
        seed_candidates = [
            t for t in reversed(list(self.recent_tracks))
            if t.youtube_video_id
        ]

        if not seed_candidates:
            return []

        # Rotate through seed tracks for variety
        # Try up to 3 different seeds
        attempts = min(3, len(seed_candidates))

        for attempt in range(attempts):
            seed_index = (self._last_seed_index + attempt) % len(seed_candidates)
            seed_track = seed_candidates[seed_index]

            logger.debug(
                "Autoplay: Trying YouTube Mix with seed %d/%d: %s",
                attempt + 1,
                attempts,
                seed_track.title
            )

            tracks = await self._get_youtube_mix_tracks(
                seed_track.youtube_video_id,
                requested_by,
                count
            )

            if tracks:
                # Update last seed index for next time
                self._last_seed_index = (seed_index + 1) % len(seed_candidates)
                return tracks

        return []

    async def _get_youtube_mix_tracks(
        self, video_id: str, requested_by: str, count: int
    ) -> List[Track]:
        """
        Get tracks from YouTube Mix/Radio playlist.
        YouTube generates a "Mix" playlist with RD prefix based on video ID.
        """
        if not video_id:
            return []

        try:
            # YouTube Mix playlist URL
            mix_url = f"https://www.youtube.com/watch?v={video_id}&list=RD{video_id}"

            logger.debug("Fetching YouTube Mix for video_id=%s", video_id)

            # Resolve the mix playlist - fetch more than needed for filtering
            tracks_result, _ = await youtube.resolve_playlist(
                mix_url, requested_by, limit=count + 15
            )

            if not tracks_result:
                logger.debug("YouTube Mix returned no tracks for video_id=%s", video_id)
                return []

            # Collect video IDs of recently played tracks to avoid repetition
            recent_video_ids = {
                t.youtube_video_id
                for t in self.recent_tracks
                if t.youtube_video_id
            }

            # Filter and add variety
            tracks: List[Track] = []
            for track in tracks_result:
                if len(tracks) >= count:
                    break

                track_video_id = _extract_video_id(track.webpage_url)

                # Skip the seed track
                if track_video_id == video_id:
                    continue

                # Skip recently played tracks
                if track_video_id in recent_video_ids:
                    continue

                # Skip already recommended tracks
                if track_video_id and track_video_id in self.recommended_ids:
                    continue

                track.source = "autoplay"
                tracks.append(track)
                if track_video_id:
                    self.recommended_ids.add(track_video_id)

            if tracks:
                logger.info(
                    "Autoplay: Got %d tracks from YouTube Mix for video_id=%s",
                    len(tracks),
                    video_id
                )

            return tracks

        except Exception as e:
            logger.warning("YouTube Mix failed for video_id=%s: %s", video_id, e)
            return []

    async def _get_search_based_recommendations(
        self, requested_by: str, count: int
    ) -> List[Track]:
        """
        Fallback: Search for similar tracks using artist/genre information.
        Tries multiple search strategies for variety.
        """
        if not self.recent_tracks:
            return []

        # Get recent tracks with artist information
        tracks_with_artists = [
            t for t in reversed(list(self.recent_tracks))
            if t.artist
        ]

        if not tracks_with_artists:
            return []

        # Pick a random recent track for variety
        seed_track = random.choice(tracks_with_artists[:5])

        search_queries = [
            f"{seed_track.artist} radio",
            f"{seed_track.artist} mix",
            f"{seed_track.artist} similar songs",
        ]

        # Try each search query
        for search_query in search_queries:
            try:
                logger.debug("Autoplay: Trying search: %s", search_query)

                # Search for the query
                track = await youtube.resolve(search_query, requested_by)

                # Extract video ID and check if it's a playlist/mix
                video_id = _extract_video_id(track.webpage_url)
                if not video_id:
                    continue

                # Try to get tracks from this as a seed
                tracks = await self._get_youtube_mix_tracks(
                    video_id, requested_by, count
                )

                if tracks:
                    logger.info(
                        "Autoplay: Got %d tracks from search-based recommendation: %s",
                        len(tracks),
                        search_query
                    )
                    return tracks

            except Exception as e:
                logger.debug("Search-based recommendation failed for '%s': %s", search_query, e)
                continue

        return []

    def clear_history(self) -> None:
        """Clear playback history and recommended IDs."""
        self.recent_tracks.clear()
        self.recommended_ids.clear()
        self._last_seed_index = 0
        logger.debug("Autoplay history cleared for guild %s", self.guild_id)


# Global registry of AutoplayManagers per guild
_autoplay_managers: Dict[int, AutoplayManager] = {}


def get_autoplay_manager(guild_id: int) -> AutoplayManager:
    """Get or create an AutoplayManager for a guild."""
    if guild_id not in _autoplay_managers:
        _autoplay_managers[guild_id] = AutoplayManager(guild_id)
    return _autoplay_managers[guild_id]


def remove_autoplay_manager(guild_id: int) -> None:
    """Remove the AutoplayManager for a guild."""
    if guild_id in _autoplay_managers:
        del _autoplay_managers[guild_id]


def _extract_video_id(url: str) -> Optional[str]:
    """Extract YouTube video ID from URL."""
    if not url:
        return None

    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None
