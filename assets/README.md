# Warning Audio Clips

Provide localized idle warning clips here:

- `assets/warn_tr_.wav` (fallback: `assets/warn_tr.wav`)

These files are played in the voice channel 15 minutes before idle auto-disconnect.

If a file is missing or empty, the bot falls back to sending a localized text warning
in the interaction channel and still disconnects on timeout.
