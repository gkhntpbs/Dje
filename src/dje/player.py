import asyncio
import discord
import os
import time
import re
import hashlib
import functools
import logging
import random
import yt_dlp
from discord import VoiceClient
from typing import Optional, Dict
from .tracks import Track
from . import audio
from . import settings
from .i18n import t

# Directory for downloaded audio files
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOWNLOAD_DIR = os.path.join(PROJECT_ROOT, "downloads")
ASSETS_DIR = os.path.join(PROJECT_ROOT, "assets")
WARN_AUDIO_FILES = {
    "tr": ("warn_tr_.wav", "warn_tr.wav"),
    "en": ("warn_en.mp3",),
}

# Ensure download directory exists
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Maximum duration in seconds (20 minutes)
MAX_DURATION_SECONDS = 20 * 60

# Cache: video_id -> (filepath, last_access_time)
_audio_cache: Dict[str, tuple[str, float]] = {}

# Track files scheduled for deletion: {filepath: deletion_time}
_scheduled_deletions: dict[str, float] = {}


def extract_video_id(url: str) -> Optional[str]:
    """Extract YouTube video ID from URL."""
    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})',
        r'^([a-zA-Z0-9_-]{11})$'  # Direct video ID
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    # For search queries, create a hash
    return hashlib.md5(url.encode()).hexdigest()[:16]


def _get_warn_audio_path(locale: str) -> Optional[str]:
    filenames = WARN_AUDIO_FILES.get(locale, WARN_AUDIO_FILES["tr"])
    if isinstance(filenames, str):
        filenames = (filenames,)
    for filename in filenames:
        path = os.path.join(ASSETS_DIR, filename)
        if not os.path.exists(path):
            continue
        try:
            if os.path.getsize(path) <= 0:
                continue
        except OSError:
            continue
        return path
    return None


from collections import deque

class GuildPlayer:
    def __init__(self, guild_id: int, bot: discord.Client, interaction_channel: discord.abc.Messageable):
        self.guild_id = guild_id
        self.bot = bot
        self.interaction_channel = interaction_channel
        self.queue: deque[Track] = deque()
        self.override_queue: deque[Track] = deque()
        self.insert_next_queue: deque[Track] = deque()
        self.queue_event = asyncio.Event()
        self.history: deque[Track] = deque(maxlen=50)
        self.current: Optional[Track] = None
        self.next_event = asyncio.Event()
        self.task: Optional[asyncio.Task] = None
        self.idle_task: Optional[asyncio.Task] = None
        self.warn_task: Optional[asyncio.Task] = None
        self.warn_playing = False
        self.shuffle_recent: deque[str] = deque(maxlen=10)
        self.loop_track: Optional[Track] = None
        self.original_queue_snapshot: list[Track] = []

    @property
    def voice_client(self) -> Optional[VoiceClient]:
        guild = self.bot.get_guild(self.guild_id)
        if guild:
            return guild.voice_client
        return None

    async def _get_locale(self) -> str:
        settings_data = await settings.get_guild_settings(self.guild_id)
        return settings_data.locale

    def is_idle(self) -> bool:
        vc = self.voice_client
        if not vc or not vc.is_connected():
            return False
        if vc.is_playing() or vc.is_paused():
            return False
        if self.override_queue or self.insert_next_queue or self.queue:
            return False
        if self.current is not None:
            return False
        return True

    def _stop_warning_playback(self) -> None:
        vc = self.voice_client
        if self.warn_playing and vc and vc.is_playing():
            vc.stop()
        self.warn_playing = False

    def stop_warning_playback(self) -> None:
        self._stop_warning_playback()

    def cancel_idle_disconnect(self) -> None:
        if self.warn_task and not self.warn_task.done():
            self.warn_task.cancel()
        if self.idle_task and not self.idle_task.done():
            self.idle_task.cancel()
        self.warn_task = None
        self.idle_task = None

    async def schedule_idle_disconnect(self) -> None:
        self.cancel_idle_disconnect()
        settings_data = await settings.get_guild_settings(self.guild_id)
        if not settings_data.auto_disconnect_enabled:
            return
        if not self.is_idle():
            return
        timeout_minutes = settings_data.auto_disconnect_minutes
        warn_minutes = settings_data.auto_disconnect_warn_minutes
        if timeout_minutes <= 0:
            return
        if warn_minutes < 0:
            warn_minutes = 0
        warn_at = timeout_minutes - warn_minutes
        if warn_at >= 1:
            self.warn_task = asyncio.create_task(self._idle_warn_after(warn_at * 60))
        self.idle_task = asyncio.create_task(self._idle_disconnect_after(timeout_minutes * 60))

    async def _idle_warn_after(self, delay_seconds: int) -> None:
        try:
            await asyncio.sleep(delay_seconds)
            settings_data = await settings.get_guild_settings(self.guild_id)
            if not settings_data.auto_disconnect_enabled:
                return
            if not self.is_idle():
                return
            await self._play_warning_clip(settings_data.auto_disconnect_warn_minutes)
        except asyncio.CancelledError:
            return
        finally:
            self.warn_task = None

    async def _idle_disconnect_after(self, delay_seconds: int) -> None:
        try:
            await asyncio.sleep(delay_seconds)
            settings_data = await settings.get_guild_settings(self.guild_id)
            if not settings_data.auto_disconnect_enabled:
                return
            if not self.is_idle():
                return
            if self.warn_task and not self.warn_task.done():
                self.warn_task.cancel()
                self.warn_task = None
            await self.stop()
            vc = self.voice_client
            if vc and vc.is_connected():
                await vc.disconnect()
            if self.interaction_channel:
                locale = settings_data.locale
                await self.interaction_channel.send(t("autodisc.disconnected_text", locale))
        except asyncio.CancelledError:
            return
        finally:
            self.idle_task = None

    async def _play_warning_clip(self, warn_minutes: int) -> None:
        vc = self.voice_client
        if not vc or not vc.is_connected():
            return
        if not self.is_idle():
            return
        settings_data = await settings.get_guild_settings(self.guild_id)
        locale = settings_data.locale
        clip_path = _get_warn_audio_path(locale)
        if not clip_path:
            if self.interaction_channel:
                await self.interaction_channel.send(
                    t("autodisc.warn_text", locale, minutes=warn_minutes)
                )
            return
        ffmpeg_path = audio.get_ffmpeg_executable()
        try:
            source = discord.FFmpegPCMAudio(clip_path, executable=ffmpeg_path)
            self.warn_playing = True

            def _after(_: Optional[Exception]) -> None:
                self.warn_playing = False

            vc.play(source, after=_after)
        except Exception:
            self.warn_playing = False
            if self.interaction_channel:
                await self.interaction_channel.send(
                    t("autodisc.warn_text", locale, minutes=warn_minutes)
                )

    async def start(self) -> None:
        """Starts the playback loop if not already running."""
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self.player_loop())

    async def stop(self) -> None:
        """Stops playback, clears queue, and cancels the loop."""
        self.queue.clear()
        self.override_queue.clear()
        self.insert_next_queue.clear()
        self.history.clear()
        self.current = None
        self._stop_warning_playback()
        if self.voice_client:
            if self.voice_client.is_playing() or self.voice_client.is_paused():
                self.voice_client.stop()
        if self.task:
            self.task.cancel()
            self.task = None

    def skip(self) -> None:
        """Skips the current track."""
        if self.voice_client and (self.voice_client.is_playing() or self.voice_client.is_paused()):
            self.voice_client.stop()
            
    def pause(self) -> bool:
        """Pauses playback. Returns True if successful."""
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.pause()
            return True
        return False

    def resume(self) -> bool:
        """Resumes playback. Returns True if successful."""
        if self.voice_client and self.voice_client.is_paused():
            self.voice_client.resume()
            return True
        return False
        
    async def play_previous(self) -> Optional[Track]:
        """Stop current and play previous track from history."""
        if not self.history:
            return None

        # Get last track from history
        prev_track = self.history.pop()

        # Override has precedence over insert-next and normal queue.
        self.override_queue.appendleft(prev_track)
        self.queue_event.set()

        # Skip current track (which will push current to history in loop, but we want to avoid duplicates if possible?
        # Requirement: "push the current track into history".
        # So effective history: [..., Current]. Queue: [Prev, Next...].
        # Playing: Prev.
        # This is correct.
        self.skip()
        return prev_track

    async def apply_shuffle(self) -> None:
        """Shuffle the main queue based on guild settings."""
        settings_data = await settings.get_guild_settings(self.guild_id)
        shuffle_mode = settings_data.shuffle_mode

        if shuffle_mode == "none" or not self.queue:
            return

        queue_list = list(self.queue)

        if shuffle_mode == "full":
            # Completely random
            random.shuffle(queue_list)
        elif shuffle_mode == "smart":
            # Don't pick recently played tracks
            # Prioritize non-recent tracks
            recent_ids = set(self.shuffle_recent)
            non_recent = [t for t in queue_list if extract_video_id(t.webpage_url) not in recent_ids]
            recent = [t for t in queue_list if extract_video_id(t.webpage_url) in recent_ids]

            random.shuffle(non_recent)
            random.shuffle(recent)
            queue_list = non_recent + recent  # Put recent tracks at end

        self.queue = deque(queue_list)

    async def enqueue(self, track: Track) -> None:
        """Adds a track to the queue and ensures the loop is running."""
        await self.enqueue_items([track], mode="append")

    async def enqueue_items(self, tracks: list[Track], mode: str = "append") -> None:
        """Adds tracks to the queue or insert-next buffer and ensures the loop is running."""
        if not tracks:
            return
        self.cancel_idle_disconnect()
        self._stop_warning_playback()
        enqueue_mode = mode
        if enqueue_mode == "insert_next":
            has_pending = (
                self.current is not None
                or self.override_queue
                or self.insert_next_queue
                or self.queue
            )
            if not has_pending:
                enqueue_mode = "append"
        if enqueue_mode == "insert_next":
            self.insert_next_queue.extend(tracks)
        else:
            self.queue.extend(tracks)

        # Apply shuffle if enabled (only to normal queue)
        settings_data = await settings.get_guild_settings(self.guild_id)
        if enqueue_mode == "append" and settings_data.shuffle_mode != "none":
            await self.apply_shuffle()

        # Update queue snapshot for loop
        if settings_data.loop_mode == "queue":
            self.original_queue_snapshot = list(self.queue)

        self.queue_event.set()
        await self.start()

    def _pop_next_track(self) -> Optional[Track]:
        # Precedence: insert_next_queue -> override_queue (e.g., /prev) -> queue.
        if self.insert_next_queue:
            return self.insert_next_queue.popleft()
        if self.override_queue:
            return self.override_queue.popleft()
        if self.queue:
            return self.queue.popleft()
        return None

    def _after_playback(self, error: Optional[Exception]) -> None:
        """Callback called by discord.py when audio finishes."""
        if error:
            logging.error("Playback error: %s", error)
        self.next_event.set()

    async def player_loop(self) -> None:
        """Main background loop."""
        await self.bot.wait_until_ready()

        while True:
            self.next_event.clear()

            # Helper to push finished track to history
            if self.current:
                self.history.append(self.current)
                # Track for smart shuffle
                video_id = extract_video_id(self.current.webpage_url)
                self.shuffle_recent.append(video_id)
            self.current = None

            try:
                # Check for track-based loop (temporary from /play loop:single)
                if self.loop_track and not (self.override_queue or self.insert_next_queue or self.queue):
                    self.queue.append(self.loop_track)
                    self.queue_event.set()

                # Check for queue loop
                settings_data = await settings.get_guild_settings(self.guild_id)
                if settings_data.loop_mode == "queue" and not (self.override_queue or self.insert_next_queue or self.queue):
                    if self.original_queue_snapshot:
                        # Re-shuffle if shuffle is on
                        if settings_data.shuffle_mode != "none":
                            snapshot_copy = self.original_queue_snapshot.copy()
                            random.shuffle(snapshot_copy)
                            self.queue.extend(snapshot_copy)
                        else:
                            self.queue.extend(self.original_queue_snapshot)
                        self.queue_event.set()

                # Check for single track loop
                if settings_data.loop_mode == "single" and self.current is None and self.history:
                    # Re-add the last played track
                    last_track = self.history[-1]
                    self.queue.append(last_track)
                    self.queue_event.set()

                # Wait for next track
                while not (self.override_queue or self.insert_next_queue or self.queue):
                    self.queue_event.clear()
                    await self.schedule_idle_disconnect()
                    await self.queue_event.wait()
                    self.cancel_idle_disconnect()
                    self._stop_warning_playback()
                
                track = self._pop_next_track()
                if not track:
                    continue
                self.current = track
                self.cancel_idle_disconnect()
                self._stop_warning_playback()

                # Ensure voice connection
                vc = self.voice_client
                if not vc or not vc.is_connected():
                    if self.interaction_channel:
                        locale = await self._get_locale()
                        await self.interaction_channel.send(t("playback.disconnected_stop", locale))
                    await self.stop()
                    return

                ffmpeg_path = audio.get_ffmpeg_executable()

                try:
                    # Check if track was marked as failed during preload
                    if track.filepath == "FAILED":
                        if self.interaction_channel:
                            locale = await self._get_locale()
                            await self.interaction_channel.send(
                                t("playback.skip_unavailable", locale, title=track.title)
                            )
                        self.next_event.set()
                        continue
                    
                    # Track should already have filepath from pre-download
                    if track.filepath and os.path.exists(track.filepath):
                        filepath = track.filepath
                    else:
                        # Fallback: download if filepath missing (for playlist items)
                        video_id = extract_video_id(track.webpage_url)
                        cached_path = get_cached_path(video_id)
                        
                        if cached_path:
                            filepath = cached_path
                        else:
                            if self.interaction_channel:
                                locale = await self._get_locale()
                                await self.interaction_channel.send(
                                    t("download.downloading", locale, title=track.title)
                                )
                            filepath = await download_track(track.webpage_url, video_id)
                            track.filepath = filepath
                    
                    # Start pre-downloading next track in background (for gapless playback)
                    asyncio.create_task(self._preload_next_track())
                    
                    # Notify now playing
                    if self.interaction_channel:
                        locale = await self._get_locale()
                        await self.interaction_channel.send(
                            t(
                                "playback.now_playing",
                                locale,
                                title=track.title,
                                requested_by=track.requested_by,
                            )
                        )
                    
                    # Play from local file
                    source = discord.FFmpegPCMAudio(
                        filepath,
                        executable=ffmpeg_path
                    )
                    
                    vc.play(source, after=self._after_playback)
                    await self.next_event.wait()

                except DurationLimitError as e:
                    if self.interaction_channel:
                        locale = await self._get_locale()
                        await self.interaction_channel.send(
                            t(
                                "errors.duration_limit_track",
                                locale,
                                title=track.title,
                                minutes=e.minutes,
                                max_minutes=e.max_minutes,
                            )
                        )
                    self.next_event.set()
                except Exception as e:
                    if self.interaction_channel:
                        locale = await self._get_locale()
                        if str(e) == "Download failed":
                            await self.interaction_channel.send(t("errors.download_failed_generic", locale))
                        else:
                            await self.interaction_channel.send(
                                t("errors.playback_error", locale, title=track.title, error=e)
                            )
                    self.next_event.set()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.exception("Error in player loop")
                await asyncio.sleep(1)

    async def _preload_next_track(self) -> None:
        """Pre-download the next track in queue for gapless playback."""
        try:
            # Peek at next track without removing it
            if not (self.override_queue or self.insert_next_queue or self.queue):
                return

            queue_list = (
                list(self.override_queue)
                + list(self.insert_next_queue)
                + list(self.queue)
            )
            
            # Try to preload tracks in order, skipping unavailable ones
            for idx, next_track in enumerate(queue_list):
                if not next_track:
                    continue
                logging.info("Preload candidate: %s", next_track.title)
                
                # If already downloaded, we're done
                if next_track.filepath and os.path.exists(next_track.filepath):
                    logging.info("Next track already cached: %s", next_track.title)
                    return
                
                # Try to download this track
                try:
                    video_id = extract_video_id(next_track.webpage_url)
                    cached_path = get_cached_path(video_id)
                    
                    if cached_path:
                        next_track.filepath = cached_path
                        logging.info("Next track preloaded from cache: %s", next_track.title)
                        return
                    else:
                        filepath = await download_track(next_track.webpage_url, video_id)
                        next_track.filepath = filepath
                        logging.info("Next track preloaded: %s", next_track.title)
                        return
                        
                except Exception as e:
                    # This track failed, mark it and try next one
                    logging.warning(
                        "Preload failed for %s (skipping): %s",
                        next_track.title,
                        str(e)[:100],
                    )
                    # Mark as failed so player_loop can skip it
                    next_track.filepath = "FAILED"
                    continue
            
            # If we got here, all tracks in queue failed
            logging.warning("No upcoming tracks could be preloaded")
                
        except Exception as e:
            logging.exception("Preload error")


class DurationLimitError(Exception):
    """Raised when a track exceeds the maximum duration."""
    def __init__(self, minutes: int, max_minutes: int) -> None:
        super().__init__(f"{minutes}>{max_minutes}")
        self.minutes = minutes
        self.max_minutes = max_minutes


def get_cached_path(video_id: str) -> Optional[str]:
    """Check if a video is cached and return its path if valid."""
    if video_id in _audio_cache:
        filepath, last_access = _audio_cache[video_id]
        # Check if file still exists and is not scheduled for imminent deletion
        if os.path.exists(filepath):
            # Update last access time
            _audio_cache[video_id] = (filepath, time.time())
            # Reschedule deletion (extend cache lifetime)
            schedule_deletion(filepath, 15 * 60)
            return filepath
        else:
            # File was deleted, remove from cache
            del _audio_cache[video_id]
    return None


async def download_track(url: str, video_id: str) -> str:
    """
    Downloads audio from YouTube URL and returns the local filepath.
    Uses yt-dlp to download the best audio format.
    Checks duration before downloading.
    """
    # Use video_id for consistent filename (enables caching)
    output_template = os.path.join(DOWNLOAD_DIR, f"{video_id}.%(ext)s")
    final_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.mp3")
    
    # If file already exists (race condition check), return it
    if os.path.exists(final_path):
        _audio_cache[video_id] = (final_path, time.time())
        schedule_deletion(final_path, 15 * 60)
        logging.info("Download cache hit for video_id=%s", video_id)
        return final_path
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_template,
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        # Critical: Use android client for better compatibility
        'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'ffmpeg_location': audio.get_ffmpeg_executable(),
    }
    
    loop = asyncio.get_event_loop()
    
    def do_download():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # First, extract info without downloading to check duration
            logging.info("Fetching metadata for download video_id=%s", video_id)
            info = ydl.extract_info(url, download=False)
            
            if info:
                duration = info.get('duration', 0)
                if duration and duration > MAX_DURATION_SECONDS:
                    minutes = int(duration // 60)
                    max_minutes = int(MAX_DURATION_SECONDS // 60)
                    raise DurationLimitError(minutes, max_minutes)
            
            # Now download
            logging.info("Starting download video_id=%s", video_id)
            info = ydl.extract_info(url, download=True)
            if info:
                return final_path
        return None
    
    filepath = await loop.run_in_executor(None, do_download)
    
    if not filepath or not os.path.exists(filepath):
        logging.error("Download failed for video_id=%s", video_id)
        raise Exception("Download failed")

    # Add to cache
    _audio_cache[video_id] = (filepath, time.time())
    
    # Schedule deletion after 15 minutes
    schedule_deletion(filepath, 15 * 60)
    
    logging.info("Download completed video_id=%s", video_id)
    return filepath


def schedule_deletion(filepath: str, delay_seconds: int) -> None:
    """Schedule a file to be deleted after delay_seconds."""
    deletion_time = time.time() + delay_seconds
    _scheduled_deletions[filepath] = deletion_time
    
    async def delete_later():
        await asyncio.sleep(delay_seconds)
        try:
            # Only delete if this is still the scheduled time (not extended)
            if (
                filepath in _scheduled_deletions
                and _scheduled_deletions[filepath] <= time.time()
            ):
                if os.path.exists(filepath):
                    os.remove(filepath)
                    logging.info("Deleted cached file: %s", filepath)
                # Remove from cache
                for vid, (path, _) in list(_audio_cache.items()):
                    if path == filepath:
                        del _audio_cache[vid]
                        break
                if filepath in _scheduled_deletions:
                    del _scheduled_deletions[filepath]
        except Exception as e:
            logging.error("Delete error %s: %s", filepath, e)
    
    asyncio.create_task(delete_later())


def _cleanup_old_downloads_sync() -> int:
    removed_count = 0
    if os.path.exists(DOWNLOAD_DIR):
        for filename in os.listdir(DOWNLOAD_DIR):
            filepath = os.path.join(DOWNLOAD_DIR, filename)
            if os.path.isfile(filepath):
                file_age = time.time() - os.path.getmtime(filepath)
                if file_age > 15 * 60:
                    os.remove(filepath)
                    removed_count += 1
                    logging.info("Removed stale download: %s", filename)
    return removed_count


async def cleanup_old_downloads() -> None:
    """Cleanup any leftover downloads on startup."""
    try:
        removed_count = await asyncio.to_thread(_cleanup_old_downloads_sync)
        if removed_count:
            logging.info("Startup cleanup removed %d files", removed_count)
    except Exception as e:
        logging.error("Cleanup error: %s", e)


def _clear_all_downloads_sync() -> int:
    deleted_count = 0
    logging.info("Clearing all downloads")
    if os.path.exists(DOWNLOAD_DIR):
        for filename in os.listdir(DOWNLOAD_DIR):
            filepath = os.path.join(DOWNLOAD_DIR, filename)
            if os.path.isfile(filepath):
                try:
                    os.remove(filepath)
                    deleted_count += 1
                    logging.info("Deleted file: %s", filename)
                except Exception as e:
                    logging.error("Failed to delete %s: %s", filename, e)
    return deleted_count


async def clear_all_downloads() -> int:
    """Clear all files in the downloads directory. Returns the number of files deleted."""
    global _audio_cache, _scheduled_deletions

    try:
        deleted_count = await asyncio.to_thread(_clear_all_downloads_sync)

        _audio_cache.clear()
        _scheduled_deletions.clear()

        logging.info("Cleared %d files from downloads", deleted_count)
        return deleted_count
    except Exception as e:
        logging.error("Cleanup error: %s", e)
        return 0


def get_active_filepaths(players_dict: dict) -> set:
    """Get set of filepaths that are currently playing or in queue."""
    active_paths = set()

    for guild_id, player in players_dict.items():
        if player.current and player.current.filepath:
            active_paths.add(player.current.filepath)

        try:
            for track in list(player.queue):
                if track.filepath:
                    active_paths.add(track.filepath)
        except:
            pass
    
    return active_paths


def _cleanup_inactive_downloads_sync(active_paths: set) -> tuple[int, list[str]]:
    """Synchronous helper for cleanup_inactive_downloads."""
    deleted_count = 0
    deleted_files = []

    if not os.path.exists(DOWNLOAD_DIR):
        return 0, []

    filenames = [
        filename
        for filename in os.listdir(DOWNLOAD_DIR)
        if os.path.isfile(os.path.join(DOWNLOAD_DIR, filename))
    ]
    if not filenames:
        return 0, []

    logging.info("Starting inactive download cleanup")
    for filename in filenames:
        filepath = os.path.join(DOWNLOAD_DIR, filename)

        if filepath not in active_paths:
            try:
                os.remove(filepath)
                deleted_count += 1
                deleted_files.append(filepath)
                logging.info("Deleted inactive file: %s", filename)
            except Exception as e:
                logging.error("Failed to delete %s: %s", filename, e)

    return deleted_count, deleted_files


async def cleanup_inactive_downloads(players_dict: dict) -> int:
    """Delete downloads that are not currently playing or in any queue. Returns number of files deleted."""
    global _audio_cache, _scheduled_deletions

    active_paths = get_active_filepaths(players_dict)

    try:
        deleted_count, deleted_files = await asyncio.to_thread(
            _cleanup_inactive_downloads_sync,
            active_paths
        )

        for filepath in deleted_files:
            for vid, (path, _) in list(_audio_cache.items()):
                if path == filepath:
                    del _audio_cache[vid]
                    break

            if filepath in _scheduled_deletions:
                del _scheduled_deletions[filepath]

        if deleted_count:
            logging.info("Inactive cleanup removed %d files", deleted_count)
        return deleted_count
    except Exception as e:
        logging.error("Cleanup error: %s", e)
        return 0


def get_downloads_size_mb() -> float:
    """Get total size of downloads folder in MB."""
    total_size = 0
    try:
        if os.path.exists(DOWNLOAD_DIR):
            for filename in os.listdir(DOWNLOAD_DIR):
                filepath = os.path.join(DOWNLOAD_DIR, filename)
                if os.path.isfile(filepath):
                    total_size += os.path.getsize(filepath)
    except:
        pass
    return total_size / (1024 * 1024)
