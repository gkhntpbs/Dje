#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "Please run ./setup.sh first."
  exit 1
fi

. .venv/bin/activate

LOCAL_FFMPEG="./bin/ffmpeg"
if ! { [ -x "$LOCAL_FFMPEG" ] || command -v ffmpeg >/dev/null 2>&1; }; then
  echo "Warning: ffmpeg not found."
fi

python -m dje
