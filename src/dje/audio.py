import discord
from discord import VoiceClient
import shutil
import os
import platform


def _is_executable(path: str) -> bool:
    return os.path.exists(path) and os.access(path, os.X_OK)


def _is_elf(path: str) -> bool:
    try:
        with open(path, "rb") as handle:
            return handle.read(4) == b"\x7fELF"
    except OSError:
        return False


class AudioError(Exception):
    """Custom exception for audio errors."""
    pass


def get_base_path() -> str:
    """Returns the project root directory."""
    # src/dje/audio.py -> src/dje -> src -> root
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_ffmpeg_executable() -> str:
    """Finds the ffmpeg executable path."""
    system = platform.system()

    base_path = get_base_path()
    if system == "Windows":
        local_bin = os.path.join(base_path, "bin", "ffmpeg.exe")
        if _is_executable(local_bin):
            return local_bin
    else:
        local_bin = os.path.join(base_path, "bin", "ffmpeg")
        if _is_executable(local_bin):
            if system == "Linux" and not _is_elf(local_bin):
                # Skip macOS binary on Linux; fall back to PATH/system
                pass
            else:
                return local_bin

    # 2. Check PATH
    path = shutil.which("ffmpeg")
    if path:
        return path
        
    # 3. Common paths fallback
    common_paths = [
        "/opt/homebrew/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
    ]
    for p in common_paths:
        if os.path.exists(p):
            return p
    return "ffmpeg"


def load_opus_lib() -> None:
    """Explicitly loads libopus if not already loaded."""
    if discord.opus.is_loaded():
        return

    system = platform.system()

    # 1. Check project/bin for OS-specific names
    base_path = get_base_path()
    if system == "Windows":
        possible_names = ["libopus-0.dll", "libopus.dll"]
    elif system == "Darwin":
        possible_names = ["libopus.dylib"]
    else:  # Linux and others
        possible_names = ["libopus.so.0", "libopus.so"]

    for name in possible_names:
        local_lib = os.path.join(base_path, "bin", name)
        if os.path.exists(local_lib):
            try:
                discord.opus.load_opus(local_lib)
                return
            except OSError:
                continue

    # 2. Common system paths
    if system == "Windows":
        opus_paths = ["libopus-0.dll", "libopus.dll"]
    elif system == "Darwin":
        opus_paths = [
            "/opt/homebrew/lib/libopus.dylib",
            "/usr/local/lib/libopus.dylib",
        ]
    else:
        opus_paths = [
            "libopus.so.0",
            "/usr/lib/libopus.so.0",
            "/usr/lib64/libopus.so.0",
            "/usr/local/lib/libopus.so.0",
        ]
    
    for path in opus_paths:
        try:
            discord.opus.load_opus(path)
            return
        except OSError:
            continue
            
    # If we get here and it's still not loaded, discord.py might raise OpusNotLoaded later

def play_local_file(voice_client: VoiceClient, file_path: str) -> None:
    """
    Plays a local audio file on the given voice client.
    Stops any currently playing audio.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Audio file not found at: {file_path}")

    if voice_client.is_playing():
        voice_client.stop()

    ffmpeg_path = get_ffmpeg_executable()
    # verify ffmpeg is actually executable
    if ffmpeg_path == "ffmpeg" and not shutil.which("ffmpeg"):
         raise AudioError("FFmpeg executable not found. Please install ffmpeg.")

    try:
        source = discord.FFmpegPCMAudio(file_path, executable=ffmpeg_path)
        voice_client.play(source)
    except discord.ClientException as e:
        raise AudioError(f"Discord Client Exception: {e}")
    except Exception as e:
        raise AudioError(f"Playback failed: {type(e).__name__}: {e}")
