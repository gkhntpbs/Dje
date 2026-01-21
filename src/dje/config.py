import os
from dotenv import load_dotenv

load_dotenv()

# Discord configuration
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN is missing in .env")

DISCORD_GUILD_ID = os.getenv("DISCORD_GUILD_ID")

# Spotify configuration
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

# Network resilience configuration
NETWORK_BACKOFF_BASE_SEC = float(os.getenv("NETWORK_BACKOFF_BASE_SEC", "2.0"))
NETWORK_BACKOFF_MAX_SEC = float(os.getenv("NETWORK_BACKOFF_MAX_SEC", "300.0"))
NETWORK_FAIL_WINDOW_SEC = float(os.getenv("NETWORK_FAIL_WINDOW_SEC", "120.0"))
NETWORK_FAIL_THRESHOLD = int(os.getenv("NETWORK_FAIL_THRESHOLD", "5"))
ENABLE_PROCESS_RESTART_ON_NETWORK_DEAD = os.getenv("ENABLE_PROCESS_RESTART_ON_NETWORK_DEAD", "false").lower() == "true"

# HTTP timeout configuration (seconds)
AIOHTTP_TOTAL_TIMEOUT_SEC = float(os.getenv("AIOHTTP_TOTAL_TIMEOUT_SEC", "60.0"))
AIOHTTP_CONNECT_TIMEOUT_SEC = float(os.getenv("AIOHTTP_CONNECT_TIMEOUT_SEC", "10.0"))

# DNS resolver configuration
ENABLE_AIODNS_RESOLVER = os.getenv("ENABLE_AIODNS_RESOLVER", "true").lower() == "true"

# WARP/VPN workaround configuration
# Set to true to disable SSL verification for Discord connections (use when WARP causes SSL errors)
DISABLE_DISCORD_SSL_VERIFY = os.getenv("DISABLE_DISCORD_SSL_VERIFY", "false").lower() == "true"

# Custom DNS servers to use (comma-separated, e.g., "8.8.8.8,1.1.1.1")
# Helps bypass WARP DNS issues
CUSTOM_DNS_SERVERS = os.getenv("CUSTOM_DNS_SERVERS", "8.8.8.8,8.8.4.4,1.1.1.1,1.0.0.1")

# Audio quality configuration
# Format: "opus" (recommended, smaller files, no re-encoding) or "mp3" (legacy)
DJE_AUDIO_FORMAT = os.getenv("DJE_AUDIO_FORMAT", "opus").lower()
# Bitrate in kbps (64-320)
DJE_AUDIO_BITRATE = os.getenv("DJE_AUDIO_BITRATE", "128")
# Enable audio normalization (loudnorm filter) for consistent volume
DJE_AUDIO_NORMALIZE = os.getenv("DJE_AUDIO_NORMALIZE", "false").lower() == "true"
# Enable verbose audio debugging logs
DJE_AUDIO_DEBUG = os.getenv("DJE_AUDIO_DEBUG", "false").lower() == "true"
