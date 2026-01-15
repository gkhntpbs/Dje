# Binaries Directory

This directory contains standalone executables and libraries required for the bot to run independently of the system configuration.

## Contents
- `ffmpeg`: The FFmpeg executable for audio processing.
- `libopus.dylib` (or .so/.dll): The Opus codec library for Discord voice.

## Usage
The bot checks this directory **first** before looking at system paths. 
If you move this project to another machine (e.g. Linux server), replace these files with the appropriate binaries for that OS:
- Linux: `ffmpeg` binary and `libopus.so`
- Windows: `ffmpeg.exe` and `libopus.dll`
