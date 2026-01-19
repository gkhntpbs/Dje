import asyncio
import functools
import logging
import yt_dlp
from typing import List, Tuple
from .tracks import Track

# Suppress noise
yt_dlp.utils.bug_reports_message = lambda *args, **kwargs: ''

logger = logging.getLogger(__name__)

YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'extract_flat': False,
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    # 'source_address': '0.0.0.0', # Disabled to better support IPv6 and avoid rate limits
}

class YouTubeError(Exception):
    pass

async def resolve(query: str, requested_by: str) -> Track:
    """
    Resolves a query or URL to a single Track object.
    Runs blocking yt-dlp code in a separate thread.
    """
    loop = asyncio.get_running_loop()

    try:
        with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ydl:
            partial = functools.partial(ydl.extract_info, query, download=False)
            data = await loop.run_in_executor(None, partial)

        if not data:
            raise YouTubeError("No information found for query.")

        # If it's a playlist or search result, get the first entry
        if 'entries' in data:
            data = data['entries'][0]

        return _create_track(data, requested_by)
    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e).lower()
        # Check for DNS-related errors
        if any(keyword in error_msg for keyword in ['dns', 'nodename', 'name resolution', 'getaddrinfo']):
            logger.error("DNS resolution failed for YouTube query. Likely VPN/WARP issue: %s", e)
            raise YouTubeError(
                "DNS resolution failed - check your WARP/VPN connection. "
                "YouTube may be unreachable."
            )
        raise YouTubeError(f"Failed to resolve track: {str(e)}")
    except Exception as e:
        raise YouTubeError(f"Failed to resolve track: {str(e)}")

async def resolve_playlist(playlist_url: str, requested_by: str, limit: int = 50) -> Tuple[List[Track], int]:
    """
    Resolves a YouTube playlist URL to a list of Track objects.
    Returns (tracks, skipped_count).
    """
    loop = asyncio.get_running_loop()

    opts = YTDL_OPTIONS.copy()
    opts.update({
        'noplaylist': False,
        'extract_flat': 'in_playlist',  # Extract video info quickly, don't download
    })

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            partial = functools.partial(ydl.extract_info, playlist_url, download=False)
            data = await loop.run_in_executor(None, partial)

        if not data or 'entries' not in data:
            raise YouTubeError("Could not find playlist entries.")

        tracks = []
        skipped = 0
        entries = data['entries']

        # Handle generator if entries is a generator
        if not isinstance(entries, list):
            try:
                entries = list(entries)
            except:
                raise YouTubeError("Failed to list entries.")

        for entry in entries:
            if len(tracks) >= limit:
                break

            # Skip private/unavailable videos
            if not entry:
                skipped += 1
                continue

            # extract_flat='in_playlist' usually returns reduced info.
            # We ensure we have at least a url and title.
            if not entry.get('url') and not entry.get('id'):
                skipped += 1
                continue

            try:
                track = _create_track(entry, requested_by)
                tracks.append(track)
            except:
                skipped += 1
                continue

        return tracks, skipped

    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e).lower()
        # Check for DNS-related errors
        if any(keyword in error_msg for keyword in ['dns', 'nodename', 'name resolution', 'getaddrinfo']):
            logger.error("DNS resolution failed for YouTube playlist. Likely VPN/WARP issue: %s", e)
            raise YouTubeError(
                "DNS resolution failed - check your WARP/VPN connection. "
                "YouTube may be unreachable."
            )
        raise YouTubeError(f"Failed to resolve playlist: {str(e)}")
    except Exception as e:
        raise YouTubeError(f"Failed to resolve playlist: {str(e)}")

def _create_track(data: dict, requested_by: str) -> Track:
    """Helper to create a Track object from yt-dlp data."""
    title = data.get('title', 'Unknown Title')
    webpage_url = data.get('webpage_url')
    
    # If using extract_flat, 'url' might be just the ID or relative path on youtube
    if not webpage_url:
        if data.get('url'):
            if 'youtube.com' in data['url'] or 'youtu.be' in data['url']:
                webpage_url = data['url']
            else:
                webpage_url = f"https://www.youtube.com/watch?v={data.get('id', data['url'])}"
        else:
            webpage_url = f"https://www.youtube.com/watch?v={data.get('id')}"

    return Track(
        title=title,
        webpage_url=webpage_url,
        stream_url=data.get('url', ''),
        duration=data.get('duration'),
        requested_by=requested_by
    )
