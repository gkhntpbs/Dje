<p align="center">
  <img src="assets/logo.png" alt="Dje logo" width="160" />
</p>

# Dje

Self-hosted Discord music bot for small servers: you run it locally, you control everything.

## What is Dje?

Dje is a self-hosted Discord music bot written in Python.

- No central server, no shared infrastructure.
- No public “one bot for everyone”.
- You run Dje on your own machine (PC, server, or VPS).
- You bring your own Discord bot token and (optionally) your own Spotify Client Credentials.
- Designed for personal and private Discord servers where you want full control and no artificial limits.

Dje is not a hosted service, and it is not a public bot you invite from a website. There is no SaaS component.

## Key Features

- YouTube playback: play by URL or search; supports playlists (limited).
- Spotify links: resolves Spotify metadata and plays via YouTube.
- Shortcut playlists: per-guild named shortcuts for quick playback.
- Localization: English and Turkish.
- Per-guild persistent settings (locale and shortcuts).
- Idle auto-disconnect with localized warning clip.
- Interactive UI: embeds and shortcut buttons.
- Fully local and self-hosted: no queue caps imposed by Dje (provider limits still apply).

## Localization

Dje currently supports:

- English (`en`)
- Turkish (`tr`)

Locale is selected per guild via `/settings language` and persisted in `data/guild_settings.json`.

Adding more languages is straightforward: extend `src/dje/i18n.py` and wire the new locale into the command choices.

## Project Philosophy

- Privacy-first: your bot runs on your machine, for your server.
- No central infrastructure: no shared backend, no shared token, no tracking service.
- Ownership: you own the Discord application, the credentials, and the runtime.
- Simple and hackable: readable Python, minimal moving parts, transparent behavior.

## Directory Structure

```
.
├── assets/                  # Repository assets
├── src/
│   └── dje/                 # Main Python package (bot + playback)
│       ├── __main__.py      # Entry point for `python -m dje`
│       ├── bot.py           # Slash commands and Discord client setup
│       ├── player.py        # Queue, playback loop, downloads/cache
│       ├── youtube.py       # YouTube resolving via yt-dlp
│       ├── spotify.py       # Spotify link parsing and resolution
│       ├── voice.py         # Voice channel connect/disconnect helpers
│       ├── settings.py      # Per-guild persisted settings
│       ├── i18n.py          # Localization strings
│       ├── ui.py            # UI components (Now Playing view with buttons)
│       └── ui_shortcuts.py  # Shortcut buttons UI
├── bin/                     # Local binaries (ffmpeg/opus; auto-installed by setup scripts)
├── .env.example             # Environment variable template
```

## Installation

### Prerequisites

- Git
- Python 3.9+ (Linux users: install `python3-venv` so `python -m venv` works)
- Discord bot token (you create the bot in the Discord Developer Portal)
- Spotify credentials (optional, required only for Spotify links):
  - `SPOTIFY_CLIENT_ID`
  - `SPOTIFY_CLIENT_SECRET`
- Linux: `sudo` access recommended so setup can install system packages

> No manual binary downloads required — `setup.bat` / `setup.sh` automatically install or download FFmpeg and the Opus library.
> If a package manager is available, the scripts use it; otherwise they download what’s needed (and keep any local binaries under `bin/`).

### Discord bot creation (high-level)

- Create a Discord application and add a bot user.
- Enable the required intents/permissions for voice and messaging as needed.
- Invite the bot to your server with the `applications.commands` scope so slash commands work.

> Discord setup guide: [SETUP_DISCORD.md](SETUP_DISCORD.md)

### Spotify client credentials

> Spotify setup guide: [SETUP_SPOTIFY.md](SETUP_SPOTIFY.md)

## Quick Start

### Windows (PowerShell or CMD)

```bat
git clone https://github.com/gkhntpbs/Dje.git
cd Dje
copy .env.example .env
notepad .env
.\setup.bat
.\run.bat
```

Note: In `.env`, set at least `DISCORD_TOKEN` (optional: `DISCORD_GUILD_ID`, Spotify credentials).

### macOS/Linux

```bash
git clone https://github.com/gkhntpbs/Dje.git
cd Dje
cp .env.example .env
chmod +x setup.sh run.sh
./setup.sh
./run.sh
```

Note: In `.env`, set at least `DISCORD_TOKEN` (optional: `DISCORD_GUILD_ID`, Spotify credentials).

### What setup does

- Creates `.venv/` and installs Python dependencies
- Ensures FFmpeg is available (uses a package manager when possible; otherwise downloads)
- Ensures the Opus library is available (package manager on macOS/Linux; downloads `libopus-0.dll` into `bin/` on Windows)
- Creates required local folders (`bin/` and `downloads/`)

### Manual venv workflow (optional)

If you prefer not to use the scripts, make sure `ffmpeg` and the Opus library are available on your system:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -U pip
pip install -e .
python -m dje
```

## Usage

1. Invite your bot to your Discord server.
2. Start Dje locally (see Quick Start).
3. Join a voice channel.
4. Use `/play` with a YouTube URL, playlist URL, Spotify URL, or a search query.

Notes:

- YouTube playlist requests are limited (currently 50 tracks per request).
- Spotify playlists/albums are limited (currently 50 tracks per request) and are resolved to YouTube playback.
- Individual tracks have a duration limit (currently 20 minutes).
- `/play` appends to the end of the queue; `/playnext` inserts as the next items.

## Commands

### Playback

- `/play <query-or-url>`: Play a track by search/URL; supports Spotify links.
- `/playnext <query-or-url>`: Insert right after the current track.
- `/pause`: Pause playback.
- `/resume`: Resume playback.
- `/skip`: Skip the current track.
- `/next`: Skip to next track (same as skip).
- `/prev`: Play the previous track from history.
- `/stop`: Stop playback and clear the queue.

### Queue Management

- `/queue`: Show previous/now playing/up next.
- `/clear`: Clear all upcoming tracks from queue.
- `/remove <position>`: Remove a specific track from queue by position.
- `/shuffle`: Apply shuffle to queue (smart/full shuffle modes available in settings).
- `/loop`: Set loop mode (off/queue/single).

### Voice

- `/join`: Join your voice channel.
- `/leave`: Leave the voice channel.

### Shortcuts

- `/shortcuts list`: List shortcuts with interactive buttons.
- `/shortcuts add <name> <url>`: Save a shortcut (YouTube/Spotify URL).
- `/shortcuts remove <name>`: Remove a shortcut.
- `/shortcuts play <name-or-number>`: Play a shortcut by name, or by number from the last list.

### Settings

- `/settings show`: Show all current guild settings.
- `/settings language <tr|en>`: Set the guild locale.
- `/settings shuffle <none|full|smart>`: Set shuffle mode.
- `/settings loop <none|queue|single>`: Set loop mode.
- `/settings autoplay <on|off>`: Enable/disable autoplay (adds similar tracks when queue is empty).
- `/settings autodisconnect <on|off>`: Enable or disable idle auto-disconnect.
- `/settings autodisconnect_minutes <minutes>`: Set idle timeout (20-360).
- `/settings autodisconnect_warning <on|off>`: Toggle warning audio before auto-disconnect.

### Info & Utilities

- `/help`: Show all available commands organized by category.
- `/info`: Show bot information, statistics, and links.
- `/timestamp`: Show current track timeline with progress bar.
- `/lyrics`: Fetch and display lyrics for the current track.
- `/invite`: Get bot invite link with proper permissions.
- `/support`: Support the developer.
- `/netinfo`: Show network health diagnostics (useful for troubleshooting VPN issues).

## Shortcuts System

Shortcuts are per-guild, named links that you can save and replay quickly.

- Add a shortcut: `/shortcuts add <name> <url>`
- List shortcuts (with buttons): `/shortcuts list`
- Play a shortcut by name: `/shortcuts play <name>`
- Play by number (after listing): `/shortcuts play 1`

Shortcuts are persisted in `data/guild_settings.json` (the `data/` directory is typically gitignored).

## Idle Auto-Disconnect

When the bot is idle (not playing and queue empty), it starts a timer. Fifteen minutes
before disconnect it plays a localized warning clip in the voice channel.

The warning audio can be toggled with `/settings autodisconnect_warning on|off`.

Defaults:

- Enabled
- Timeout: 60 minutes
- Warning audio: Enabled
- Warning time: 15 minutes before disconnect

Warning audio files live in `assets/warn_tr_.wav` (or `assets/warn_tr.wav`) and `assets/warn_en.mp3`.
If they are missing, the bot will send a localized text warning instead.

## Running on Unstable Networks

Dje is designed to run on home networks with potentially unstable connections.

### Network Resilience Features

The bot includes built-in resilience mechanisms to handle network instability:

1. **Circuit Breaker Pattern**: Automatically detects repeated network failures and enters a degraded state to prevent rate limiting
2. **Exponential Backoff**: Increases retry delays after consecutive failures to avoid hammering failing services
3. **DNS Error Detection**: Recognizes DNS resolution failures typical of VPN issues
4. **Non-blocking I/O**: All network operations run off the event loop to prevent heartbeat delays
5. **Network Diagnostics**: Use `/netinfo` command to check current network health status

### Configuration

Network resilience settings can be configured in your `.env` file:

```bash
# Exponential backoff settings (seconds)
NETWORK_BACKOFF_BASE_SEC=2.0
NETWORK_BACKOFF_MAX_SEC=300.0

# Circuit breaker: trigger OFFLINE state after N failures in time window
NETWORK_FAIL_WINDOW_SEC=120.0
NETWORK_FAIL_THRESHOLD=5

# Auto-restart bot when network is dead (requires supervisor)
ENABLE_PROCESS_RESTART_ON_NETWORK_DEAD=false

# HTTP timeout settings (seconds)
AIOHTTP_TOTAL_TIMEOUT_SEC=60.0
AIOHTTP_CONNECT_TIMEOUT_SEC=10.0

# Enable improved DNS resolver (requires aiodns package)
ENABLE_AIODNS_RESOLVER=true
```

### Troubleshooting VPN Issues

If you experience frequent disconnections or DNS errors:

**Check Network Status**:
```
/netinfo
```
This command shows:
- Current network health state (OK / DEGRADED / OFFLINE)
- Recent failure statistics
- Time since last successful connection
- Discord gateway status
- Troubleshooting recommendations

**Common Solutions**:
- ✓ Ensure your VPN is connected and stable
- ✓ Use a stable DNS resolver (1.1.1.1 or 8.8.8.8)
- ✓ Restart VPN application if issues persist
- ✓ Use ethernet connection if possible
- ✓ Consider running bot on a stable VPS/server

**Using a Process Supervisor**:

For automatic restarts on network failures, run the bot under a supervisor:

**pm2** (cross-platform):
```bash
npm install -g pm2
pm2 start run.sh --name dje --interpreter bash
pm2 logs dje
```

**systemd** (Linux):
```bash
sudo systemctl enable dje.service
sudo systemctl start dje
sudo journalctl -u dje -f
```

**launchd** (macOS):
Create `~/Library/LaunchAgents/com.dje.bot.plist` and load with `launchctl`

Set `ENABLE_PROCESS_RESTART_ON_NETWORK_DEAD=true` in your `.env` to enable automatic process exit (code 1) when the network is deemed dead, allowing the supervisor to restart the bot.

### Error Messages

**DNS Resolution Errors**:
```
DNS resolution failed - check your VPN connection.
YouTube/Spotify may be unreachable.
```
This indicates VPN is not properly routing DNS queries.

**Gateway Session Invalidated**:
```
Discord gateway: session has been invalidated
```
Discord.py will automatically reconnect. If this happens frequently, check your network stability.

**Event Loop Lag**:
```
Can't keep up, websocket is behind
```
This means the bot's event loop is blocked. The bot now uses non-blocking I/O to prevent this, but if you see this message, check `/netinfo` for diagnostics.

## License

Dje is licensed under the MIT License.

You can use, modify, and redistribute it (including commercially), as long as the license notice is preserved.

## Support

If Dje is useful to you and you want to support ongoing maintenance, you can optionally contribute here:

[☕ Buy Me a Coffee](https://www.buymeacoffee.com/gkhntpbs)

No paid features, no “pro” tier, and no obligation.

## Contributing

See `CONTRIBUTING.md`.

## Roadmap

See `ROADMAP.md`.

_Note: This project was written with the help of AI tools._
