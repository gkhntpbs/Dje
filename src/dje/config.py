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
