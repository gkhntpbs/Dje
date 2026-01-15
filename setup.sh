#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  if ! python3 -m venv .venv; then
    echo "Failed to create virtual environment. On Debian/Ubuntu: sudo apt update && sudo apt install -y python3-venv"
    exit 1
  fi
  echo "Virtual environment created."
fi

. .venv/bin/activate

python -m pip install --upgrade pip

if [ -f "requirements.txt" ]; then
  pip install -r requirements.txt
  echo "Dependencies installed from requirements.txt."
elif [ -f "pyproject.toml" ]; then
  pip install -e .
  echo "Dependencies installed from pyproject.toml (pip install -e .)."
else
  echo "Dependency file not found."
  exit 1
fi

echo "Setup completed."
