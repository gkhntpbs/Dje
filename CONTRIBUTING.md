# Contributing to Dje

Thanks for considering contributing. Dje is a self-hosted project intended to stay simple, transparent, and easy to run on personal Discord servers.

Contributions are welcome, but never expected. Small improvements are as valuable as large features.

## Philosophy

- Keep it self-hosted: avoid designs that require a hosted backend or shared infrastructure.
- Prefer boring tech: readability and maintainability over cleverness.
- Make behavior explicit: predictable runtime, clear errors, and minimal “magic”.
- Respect users’ environments: cross-platform where practical (macOS/Linux/Windows).

## How to Help

- Bug reports with clear reproduction steps
- Documentation improvements (including correcting assumptions)
- Small quality-of-life fixes
- Localization improvements (EN/TR) and new languages
- Targeted features that match the project goals

## Development Setup

### Requirements

- Python 3.9+ (Linux users: install `python3-venv` so `python -m venv` works)
- FFmpeg
  - Looks for `bin/ffmpeg` first (macOS binary included), then `ffmpeg` on your system `PATH`.
  - On Linux/Windows replace `bin/ffmpeg` with a matching binary or install FFmpeg on your system.
- Opus library (for Discord voice)
  - Looks for `bin/libopus.*` first (macOS binary included), then system `libopus`/`opus`.
  - Install via your package manager if needed (e.g., `brew install opus`, `apt install libopus0`, Windows: place a compatible `libopus.dll` in `bin/`).

### Install (editable)

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -U pip
pip install -e .
```

### Run

```bash
python -m dje
```

Alternatively, use the provided scripts: `setup.sh`/`run.sh` or `setup.bat`/`run.bat`.

## Code Style

Dje uses:

- Black formatting: `python -m black src`
- Ruff linting (E/F rules): `python -m ruff src`

Please format and lint before opening a PR.

Additional expectations:

- Python 3.9+ compatibility (unless a change explicitly targets a newer baseline and is discussed first)
- Clear naming (`snake_case` functions/variables, `PascalCase` classes)
- Small, focused modules (avoid “god files”)

## AI-Assisted Contributions

You may use AI tools to help draft code, documentation, or translations.

Guidelines:

- You are responsible for the change: review, understand, and test what you submit.
- Keep PRs readable: prefer smaller, well-scoped diffs over large rewrites.
- Do not include secrets or private code in prompts.
- If AI-produced output appears to be copied from another project or source, verify licensing compatibility before submitting.
- Mention AI assistance in the PR description when it materially shaped the change (especially for large edits).

## Localization Contributions

Localization strings currently live in `src/dje/i18n.py`.

Guidelines:

- Keep keys stable (rename only when necessary).
- Add translations for all supported locales when introducing a new key.
- Prefer concise, user-facing messages (Discord is a small UI).
- If you add a new locale:
  - Extend `SUPPORTED_LOCALES` and `translations` in `src/dje/i18n.py`.
  - Update locale choices in the slash command (see `src/dje/bot.py`).
  - Keep English (`en`) as a first-class, complete translation.

## Feature Requests vs. Pull Requests

If you want to propose a feature:

- Open an issue first for anything non-trivial (new commands, major behavior changes, architectural work).
- Describe the use case (who benefits, in what scenario) and the constraints (self-hosted, no central infra).
- Include expected UX in Discord (slash command shape, messages, error cases).

For small changes (typos, small bug fixes, minor refactors), feel free to open a PR directly.

## Pull Request Guidelines

- Keep PRs small and scoped (one problem per PR).
- Include a clear description of what changed and why.
- Document any new environment variables, commands, or behavior changes.
- Avoid committing secrets, tokens, logs, or downloaded media.

Suggested PR checklist:

- `python -m black src`
- `python -m ruff src`
- Manual sanity test of the related command(s)

## Reporting Bugs

When filing a bug report, include:

- Your OS and Python version
- How you installed and ran the bot
- The exact command(s) you used
- Any relevant log output (redact tokens)
- Whether the issue is reproducible and the smallest reproduction you can share

## No Obligation

Maintainers may decline PRs that don’t match the project direction, but the intent is always to be friendly and constructive. If you’re unsure about a change, open an issue first and we can discuss it.
