"""
Spotify metadata resolver module.
Fetches track/album/playlist metadata from Spotify and converts to YouTube search queries.
"""
import asyncio
import re
from dataclasses import dataclass
from typing import List, Tuple, Optional
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

from .config import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET

# Default limit for tracks per request
SPOTIFY_MAX_TRACKS = 50


class SpotifyError(Exception):
    """Raised when Spotify API operations fail."""
    pass


class SpotifyNotConfiguredError(SpotifyError):
    """Raised when Spotify credentials are not set."""
    pass


@dataclass
class SearchItem:
    """Represents a Spotify track's metadata for YouTube search."""
    artist_names: str
    title: str
    spotify_url: str
    duration_ms: Optional[int] = None
    isrc: Optional[str] = None
    
    def to_youtube_query(self) -> str:
        """Generate a YouTube search query from this item."""
        return f"{self.artist_names} - {self.title} official audio"


def _get_client() -> spotipy.Spotify:
    """Create and return a Spotify client using Client Credentials flow."""
    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        raise SpotifyNotConfiguredError(
            "Spotify credentials not configured. "
            "Please set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET in .env"
        )
    
    try:
        auth_manager = SpotifyClientCredentials(
            client_id=SPOTIFY_CLIENT_ID,
            client_secret=SPOTIFY_CLIENT_SECRET
        )
        return spotipy.Spotify(auth_manager=auth_manager)
    except Exception as e:
        raise SpotifyError(f"Failed to authenticate with Spotify: {e}")


def parse_spotify_url(url: str) -> Optional[Tuple[str, str]]:
    """
    Parse a Spotify URL or URI and extract type and ID.
    
    Returns:
        Tuple of (type, id) where type is 'track', 'album', or 'playlist'
        None if not a valid Spotify URL/URI
    """
    # URL patterns
    url_pattern = r'https?://open\.spotify\.com/(track|album|playlist)/([a-zA-Z0-9]+)'
    # URI pattern: spotify:type:id
    uri_pattern = r'spotify:(track|album|playlist):([a-zA-Z0-9]+)'
    
    # Try URL pattern first
    match = re.search(url_pattern, url)
    if match:
        return match.group(1), match.group(2)
    
    # Try URI pattern
    match = re.search(uri_pattern, url)
    if match:
        return match.group(1), match.group(2)
    
    return None


def _extract_track_info(track_data: dict) -> Optional[SearchItem]:
    """Extract SearchItem from Spotify track data."""
    if not track_data:
        return None
    
    # Skip local tracks
    if track_data.get('is_local', False):
        return None
    
    # Get artists
    artists = track_data.get('artists', [])
    artist_names = ', '.join(a.get('name', '') for a in artists if a.get('name'))
    
    if not artist_names:
        artist_names = "Unknown Artist"
    
    title = track_data.get('name', 'Unknown Track')
    spotify_url = track_data.get('external_urls', {}).get('spotify', '')
    duration_ms = track_data.get('duration_ms')
    
    # Try to get ISRC
    isrc = None
    external_ids = track_data.get('external_ids', {})
    if external_ids:
        isrc = external_ids.get('isrc')
    
    return SearchItem(
        artist_names=artist_names,
        title=title,
        spotify_url=spotify_url,
        duration_ms=duration_ms,
        isrc=isrc
    )


async def resolve_track(track_id: str) -> Tuple[List[SearchItem], int, Optional[str]]:
    """
    Resolve a single Spotify track.
    
    Returns:
        Tuple of (items, skipped_count, name)
    """
    loop = asyncio.get_event_loop()
    
    def _fetch():
        sp = _get_client()
        return sp.track(track_id)
    
    try:
        track_data = await loop.run_in_executor(None, _fetch)
        item = _extract_track_info(track_data)
        
        if item:
            name = f"{item.artist_names} - {item.title}"
            return [item], 0, name
        else:
            return [], 1, None
            
    except SpotifyNotConfiguredError:
        raise
    except Exception as e:
        raise SpotifyError(f"Failed to fetch track: {e}")


async def resolve_playlist(playlist_id: str, limit: int = SPOTIFY_MAX_TRACKS) -> Tuple[List[SearchItem], int, int, Optional[str]]:
    """
    Resolve a Spotify playlist.
    
    Returns:
        Tuple of (items, skipped_count, total_count, playlist_name)
    """
    loop = asyncio.get_event_loop()
    
    def _fetch():
        sp = _get_client()
        
        # Get playlist info
        playlist_info = sp.playlist(playlist_id, fields='name,tracks.total')
        playlist_name = playlist_info.get('name', 'Unknown Playlist')
        total = playlist_info.get('tracks', {}).get('total', 0)
        
        # Fetch tracks with pagination
        items = []
        skipped = 0
        offset = 0
        
        while len(items) < limit and offset < total:
            batch_limit = min(50, limit - len(items))  # Spotify API max is 50 per request
            results = sp.playlist_tracks(
                playlist_id,
                offset=offset,
                limit=batch_limit,
                fields='items(track(name,artists(name),external_urls,duration_ms,external_ids,is_local))'
            )
            
            for item in results.get('items', []):
                if len(items) >= limit:
                    break
                    
                track_data = item.get('track')
                search_item = _extract_track_info(track_data)
                
                if search_item:
                    items.append(search_item)
                else:
                    skipped += 1
            
            offset += batch_limit
            
            if not results.get('items'):
                break
        
        return items, skipped, total, playlist_name
    
    try:
        return await loop.run_in_executor(None, _fetch)
    except SpotifyNotConfiguredError:
        raise
    except Exception as e:
        raise SpotifyError(f"Failed to fetch playlist: {e}")


async def resolve_album(album_id: str, limit: int = SPOTIFY_MAX_TRACKS) -> Tuple[List[SearchItem], int, int, Optional[str]]:
    """
    Resolve a Spotify album.
    
    Returns:
        Tuple of (items, skipped_count, total_count, album_name)
    """
    loop = asyncio.get_event_loop()
    
    def _fetch():
        sp = _get_client()
        
        # Get album info
        album_info = sp.album(album_id)
        album_name = album_info.get('name', 'Unknown Album')
        album_artists = album_info.get('artists', [])
        album_artist_names = ', '.join(a.get('name', '') for a in album_artists)
        total = album_info.get('tracks', {}).get('total', 0)
        
        # Fetch tracks with pagination
        items = []
        skipped = 0
        offset = 0
        
        while len(items) < limit and offset < total:
            batch_limit = min(50, limit - len(items))
            results = sp.album_tracks(album_id, offset=offset, limit=batch_limit)
            
            for track_data in results.get('items', []):
                if len(items) >= limit:
                    break
                
                # Album tracks don't have full info, add album artist if track has no artist
                artists = track_data.get('artists', [])
                if not artists and album_artists:
                    track_data['artists'] = album_artists
                
                search_item = _extract_track_info(track_data)
                
                if search_item:
                    items.append(search_item)
                else:
                    skipped += 1
            
            offset += batch_limit
            
            if not results.get('items'):
                break
        
        display_name = f"{album_artist_names} - {album_name}" if album_artist_names else album_name
        return items, skipped, total, display_name
    
    try:
        return await loop.run_in_executor(None, _fetch)
    except SpotifyNotConfiguredError:
        raise
    except Exception as e:
        raise SpotifyError(f"Failed to fetch album: {e}")
