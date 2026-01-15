# Dje Roadmap

This roadmap is a directional guide, not a promise. Priorities may change based on maintenance cost, community needs, and upstream changes (Discord, YouTube, Spotify).

## Short term

- Improve error messages and recovery (voice disconnects, download failures, rate limits).
- Make command UX more consistent (responses, ephemerality, clearer feedback).
- Better diagnostics for missing dependencies (FFmpeg/Opus) across platforms.
- Documentation hardening (setup edge cases, common pitfalls, troubleshooting section).
- Reduce duplication in command aliases and consolidate shared logic where appropriate.

## Mid term

- More languages (expand beyond EN/TR with a clean process for adding locales).
- Discord authorization/roles: per-guild permission controls for commands and sensitive actions.
- Audio features:
  - Simple volume control
  - Audio quality improvements
- Queue improvements:
  - Pagination for large queues
  - Better playlist handling and batching behavior
- Docker improvements (optional):
  - Better image size and caching
  - Clear cross-platform FFmpeg/Opus story

## Long term

- Plugin system (future idea): allow adding providers/commands without forking the core.
- Optional web UI (future idea): local-only dashboard for status, queue, and settings.
- Provider abstractions: cleaner separation between “link resolver” and “playback source”.
- More robust persistence model (if needed) while remaining local-first and lightweight.
