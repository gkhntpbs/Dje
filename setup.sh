#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

BIN_DIR="$(pwd)/bin"
DOWNLOADS_DIR="$(pwd)/downloads"

mkdir -p "$BIN_DIR"
mkdir -p "$DOWNLOADS_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo ""
echo "========================================"
echo "      Dje Setup - Unix Install"
echo "========================================"
echo ""

# ----------------------------
# Helper Functions
# ----------------------------

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

download_file() {
    local url="$1"
    local dest="$2"
    
    echo "[download] $url"
    
    if command_exists curl; then
        if curl -L --retry 3 --retry-delay 2 --connect-timeout 30 -o "$dest" "$url" 2>/dev/null; then
            if [ -s "$dest" ]; then
                echo "[download] Success (curl)"
                return 0
            fi
        fi
    fi
    
    if command_exists wget; then
        echo "[download] curl failed, trying wget..."
        if wget --tries=3 --timeout=30 -O "$dest" "$url" 2>/dev/null; then
            if [ -s "$dest" ]; then
                echo "[download] Success (wget)"
                return 0
            fi
        fi
    fi
    
    echo "[download] ERROR: Failed to download file"
    return 1
}

detect_os() {
    local os
    os="$(uname -s)"
    case "$os" in
        Darwin) echo "macos" ;;
        Linux) echo "linux" ;;
        *) echo "unknown" ;;
    esac
}

detect_arch() {
    local arch
    arch="$(uname -m)"
    case "$arch" in
        x86_64|amd64) echo "x64" ;;
        arm64|aarch64) echo "arm64" ;;
        *) echo "unknown" ;;
    esac
}

# ----------------------------
# FFmpeg Installation
# ----------------------------

install_ffmpeg() {
    echo "[ffmpeg] Checking for FFmpeg..."
    
    # Check if we already have ffmpeg in bin
    if [ -x "$BIN_DIR/ffmpeg" ]; then
        echo "[ffmpeg] Found existing: $BIN_DIR/ffmpeg"
        return 0
    fi
    
    # Check if ffmpeg exists in system
    if command_exists ffmpeg; then
        local ffmpeg_path
        ffmpeg_path="$(command -v ffmpeg)"
        echo "[ffmpeg] Found system ffmpeg: $ffmpeg_path"
        
        if cp -p "$ffmpeg_path" "$BIN_DIR/ffmpeg" 2>/dev/null; then
            chmod +x "$BIN_DIR/ffmpeg"
            echo "[ffmpeg] Copied to $BIN_DIR/ffmpeg"
            return 0
        else
            echo "[ffmpeg] Could not copy, will use system ffmpeg"
            return 0
        fi
    fi
    
    local os
    os="$(detect_os)"
    
    echo "[ffmpeg] FFmpeg not found, installing..."
    
    case "$os" in
        macos)
            install_ffmpeg_macos
            ;;
        linux)
            install_ffmpeg_linux
            ;;
        *)
            echo "[ffmpeg] ERROR: Unsupported OS. Please install FFmpeg manually."
            return 1
            ;;
    esac
}

install_ffmpeg_macos() {
    if command_exists brew; then
        echo "[ffmpeg] Installing via Homebrew..."
        brew install ffmpeg 2>/dev/null || brew upgrade ffmpeg 2>/dev/null || true
        
        if command_exists ffmpeg; then
            cp -p "$(command -v ffmpeg)" "$BIN_DIR/ffmpeg" 2>/dev/null || true
            echo "[ffmpeg] Installed via Homebrew"
            return 0
        fi
    else
        echo "[ffmpeg] Homebrew not found, trying direct download..."
    fi
    
    # Direct download fallback for macOS
    local arch
    arch="$(detect_arch)"
    local ffmpeg_url=""
    
    # evermeet.cx provides static ffmpeg builds for macOS
    if [ "$arch" = "arm64" ]; then
        ffmpeg_url="https://evermeet.cx/ffmpeg/ffmpeg-7.1.zip"
    else
        ffmpeg_url="https://evermeet.cx/ffmpeg/ffmpeg-7.1.zip"
    fi
    
    local ffmpeg_zip="$DOWNLOADS_DIR/ffmpeg.zip"
    local ffmpeg_extract="$DOWNLOADS_DIR/ffmpeg_extracted"
    
    if download_file "$ffmpeg_url" "$ffmpeg_zip"; then
        echo "[ffmpeg] Extracting..."
        rm -rf "$ffmpeg_extract"
        mkdir -p "$ffmpeg_extract"
        unzip -o "$ffmpeg_zip" -d "$ffmpeg_extract" >/dev/null 2>&1
        
        if [ -f "$ffmpeg_extract/ffmpeg" ]; then
            cp "$ffmpeg_extract/ffmpeg" "$BIN_DIR/ffmpeg"
            chmod +x "$BIN_DIR/ffmpeg"
            echo "[ffmpeg] Installed: $BIN_DIR/ffmpeg"
            return 0
        fi
    fi
    
    echo "[ffmpeg] ERROR: Failed to install FFmpeg."
    echo "[ffmpeg] Please install Homebrew (https://brew.sh) and run: brew install ffmpeg"
    return 1
}

install_ffmpeg_linux() {
    # Try package managers
    if command_exists apt-get; then
        echo "[ffmpeg] Installing via apt..."
        sudo apt-get update -y >/dev/null 2>&1
        sudo apt-get install -y ffmpeg >/dev/null 2>&1
    elif command_exists dnf; then
        echo "[ffmpeg] Installing via dnf..."
        sudo dnf install -y ffmpeg >/dev/null 2>&1
    elif command_exists pacman; then
        echo "[ffmpeg] Installing via pacman..."
        sudo pacman -Sy --noconfirm ffmpeg >/dev/null 2>&1
    elif command_exists zypper; then
        echo "[ffmpeg] Installing via zypper..."
        sudo zypper install -y ffmpeg >/dev/null 2>&1
    elif command_exists apk; then
        echo "[ffmpeg] Installing via apk..."
        sudo apk add --no-cache ffmpeg >/dev/null 2>&1
    else
        echo "[ffmpeg] No supported package manager found."
    fi
    
    if command_exists ffmpeg; then
        cp -p "$(command -v ffmpeg)" "$BIN_DIR/ffmpeg" 2>/dev/null || true
        chmod +x "$BIN_DIR/ffmpeg" 2>/dev/null || true
        echo "[ffmpeg] Installed via package manager"
        return 0
    fi
    
    # Static build fallback
    echo "[ffmpeg] Trying static build download..."
    local arch
    arch="$(detect_arch)"
    local ffmpeg_url=""
    
    if [ "$arch" = "x64" ]; then
        ffmpeg_url="https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
    elif [ "$arch" = "arm64" ]; then
        ffmpeg_url="https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-arm64-static.tar.xz"
    else
        echo "[ffmpeg] ERROR: Unsupported architecture: $arch"
        return 1
    fi
    
    local ffmpeg_tar="$DOWNLOADS_DIR/ffmpeg.tar.xz"
    local ffmpeg_extract="$DOWNLOADS_DIR/ffmpeg_extracted"
    
    if download_file "$ffmpeg_url" "$ffmpeg_tar"; then
        echo "[ffmpeg] Extracting..."
        rm -rf "$ffmpeg_extract"
        mkdir -p "$ffmpeg_extract"
        tar -xf "$ffmpeg_tar" -C "$ffmpeg_extract" 2>/dev/null
        
        # Find ffmpeg binary
        local ffmpeg_bin
        ffmpeg_bin=$(find "$ffmpeg_extract" -name "ffmpeg" -type f -executable 2>/dev/null | head -n1)
        
        if [ -n "$ffmpeg_bin" ] && [ -f "$ffmpeg_bin" ]; then
            cp "$ffmpeg_bin" "$BIN_DIR/ffmpeg"
            chmod +x "$BIN_DIR/ffmpeg"
            echo "[ffmpeg] Installed: $BIN_DIR/ffmpeg"
            return 0
        fi
    fi
    
    echo "[ffmpeg] ERROR: Failed to install FFmpeg."
    return 1
}

# ----------------------------
# Opus Installation
# ----------------------------

install_opus() {
    echo "[opus] Checking for Opus library..."
    
    local os
    os="$(detect_os)"
    
    # Check if opus is already available
    if check_opus_exists; then
        echo "[opus] Opus library found"
        return 0
    fi
    
    echo "[opus] Opus not found, installing..."
    
    case "$os" in
        macos)
            install_opus_macos
            ;;
        linux)
            install_opus_linux
            ;;
        *)
            echo "[opus] WARNING: Unsupported OS for automatic opus installation."
            opus_manual_instructions
            return 0
            ;;
    esac
}

check_opus_exists() {
    local os
    os="$(detect_os)"
    
    if [ "$os" = "macos" ]; then
        # Check Homebrew
        if command_exists brew; then
            if brew list --versions opus >/dev/null 2>&1; then
                return 0
            fi
        fi
        # Check common paths
        for path in /usr/local/lib/libopus* /opt/homebrew/lib/libopus*; do
            if ls $path >/dev/null 2>&1; then
                return 0
            fi
        done
    elif [ "$os" = "linux" ]; then
        # Check via ldconfig
        if command_exists ldconfig; then
            if ldconfig -p 2>/dev/null | grep -q "libopus\.so"; then
                return 0
            fi
        fi
        # Check common paths
        for path in /usr/lib/libopus.so* /usr/lib64/libopus.so* /usr/local/lib/libopus.so* /usr/lib/x86_64-linux-gnu/libopus.so*; do
            if ls $path >/dev/null 2>&1; then
                return 0
            fi
        done
    fi
    
    return 1
}

install_opus_macos() {
    if command_exists brew; then
        echo "[opus] Installing via Homebrew..."
        brew install opus 2>/dev/null || brew upgrade opus 2>/dev/null || true
        
        if check_opus_exists; then
            echo "[opus] Installed via Homebrew"
            return 0
        fi
    fi
    
    opus_manual_instructions
    return 0
}

install_opus_linux() {
    # Try package managers
    if command_exists apt-get; then
        echo "[opus] Installing via apt..."
        sudo apt-get update -y >/dev/null 2>&1
        sudo apt-get install -y libopus0 libopus-dev >/dev/null 2>&1
    elif command_exists dnf; then
        echo "[opus] Installing via dnf..."
        sudo dnf install -y opus opus-devel >/dev/null 2>&1
    elif command_exists pacman; then
        echo "[opus] Installing via pacman..."
        sudo pacman -Sy --noconfirm opus >/dev/null 2>&1
    elif command_exists zypper; then
        echo "[opus] Installing via zypper..."
        sudo zypper install -y libopus0 >/dev/null 2>&1
    elif command_exists apk; then
        echo "[opus] Installing via apk..."
        sudo apk add --no-cache opus >/dev/null 2>&1
    else
        echo "[opus] No supported package manager found."
        opus_manual_instructions
        return 0
    fi
    
    if check_opus_exists; then
        echo "[opus] Installed via package manager"
        return 0
    fi
    
    opus_manual_instructions
    return 0
}

opus_manual_instructions() {
    echo ""
    echo "[opus] WARNING: Could not automatically install Opus library."
    echo "[opus] Voice playback may not work without it."
    echo ""
    echo "[opus] Manual installation options:"
    local os
    os="$(detect_os)"
    if [ "$os" = "macos" ]; then
        echo "  - Install Homebrew (https://brew.sh) and run: brew install opus"
    elif [ "$os" = "linux" ]; then
        echo "  - Debian/Ubuntu: sudo apt install libopus0"
        echo "  - Fedora: sudo dnf install opus"
        echo "  - Arch: sudo pacman -S opus"
    fi
    echo ""
    echo "[opus] Continuing setup without opus..."
}

# ----------------------------
# Python Virtual Environment
# ----------------------------

ensure_virtualenv() {
    echo "[python] Checking for Python..."
    
    if [ -d ".venv" ] && [ -f ".venv/bin/python" ]; then
        echo "[python] Found existing virtual environment."
        return 0
    fi
    
    # Find Python
    local python_cmd=""
    
    if command_exists python3; then
        python_cmd="python3"
    elif command_exists python; then
        # Check if it's Python 3
        if python --version 2>&1 | grep -q "Python 3"; then
            python_cmd="python"
        fi
    fi
    
    if [ -z "$python_cmd" ]; then
        echo "[python] ERROR: Python 3 not found!"
        echo "[python] Please install Python 3.10+ from https://python.org"
        local os
        os="$(detect_os)"
        if [ "$os" = "macos" ]; then
            echo "[python] Or use Homebrew: brew install python"
        elif [ "$os" = "linux" ]; then
            echo "[python] Or use your package manager: apt install python3 python3-venv"
        fi
        return 1
    fi
    
    echo "[python] Found Python: $python_cmd ($($python_cmd --version))"
    echo "[python] Creating virtual environment..."
    
    if ! $python_cmd -m venv .venv; then
        echo "[python] ERROR: Failed to create virtual environment."
        echo "[python] Possible solutions:"
        local os
        os="$(detect_os)"
        if [ "$os" = "linux" ]; then
            echo "  - Debian/Ubuntu: sudo apt install python3-venv"
        fi
        echo "  - Reinstall Python"
        return 1
    fi
    
    echo "[python] Virtual environment created: .venv"
    return 0
}

# ----------------------------
# Python Dependencies
# ----------------------------

install_python_deps() {
    echo "[python] Installing dependencies..."
    
    local venv_python=".venv/bin/python"
    
    if [ ! -x "$venv_python" ]; then
        echo "[python] ERROR: Venv python not found: $venv_python"
        return 1
    fi
    
    # Activate venv
    # shellcheck source=/dev/null
    . .venv/bin/activate
    
    echo "[python] Upgrading pip..."
    "$venv_python" -m pip install --upgrade pip >/dev/null 2>&1
    
    if [ -f "requirements.txt" ]; then
        echo "[python] Installing from requirements.txt..."
        "$venv_python" -m pip install -r requirements.txt
        if [ $? -ne 0 ]; then
            echo "[python] ERROR: Failed to install dependencies."
            return 1
        fi
    elif [ -f "pyproject.toml" ]; then
        echo "[python] Installing from pyproject.toml..."
        "$venv_python" -m pip install -e .
        if [ $? -ne 0 ]; then
            echo "[python] ERROR: Failed to install package."
            return 1
        fi
    else
        echo "[python] ERROR: No requirements.txt or pyproject.toml found."
        return 1
    fi
    
    echo "[python] Testing module import..."
    if "$venv_python" -c "import dje; print('[python] dje module loaded successfully')" 2>/dev/null; then
        :
    else
        echo "[python] WARNING: dje module import failed, but dependencies may still work."
    fi
    
    return 0
}

# ----------------------------
# Summary
# ----------------------------

show_summary() {
    echo ""
    echo "========================================"
    echo "     Setup Completed Successfully!"
    echo "========================================"
    echo ""
    
    if [ -x "$BIN_DIR/ffmpeg" ]; then
        echo -e "${GREEN}[OK]${NC} FFmpeg: $BIN_DIR/ffmpeg"
    elif command_exists ffmpeg; then
        echo -e "${GREEN}[OK]${NC} FFmpeg: $(command -v ffmpeg)"
    else
        echo -e "${YELLOW}[?]${NC}  FFmpeg: Not found"
    fi
    
    if check_opus_exists; then
        echo -e "${GREEN}[OK]${NC} Opus: System library"
    else
        echo -e "${YELLOW}[!]${NC}  Opus: Not found - voice may not work"
    fi
    
    echo -e "${GREEN}[OK]${NC} Python venv: $(pwd)/.venv"
    echo ""
    echo "To run the bot: ./run.sh"
    echo ""
}

# ----------------------------
# Main
# ----------------------------

main() {
    install_ffmpeg || { echo ""; echo "Setup failed at FFmpeg installation."; exit 1; }
    install_opus || { echo ""; echo "Setup failed at Opus installation."; exit 1; }
    ensure_virtualenv || { echo ""; echo "Setup failed at virtual environment creation."; exit 1; }
    install_python_deps || { echo ""; echo "Setup failed at dependency installation."; exit 1; }
    show_summary
}

main
