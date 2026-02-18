#!/bin/bash

# Navigate to script directory
cd "$(dirname "$0")"

echo "========================================"
echo "    Live Translation Bridge - Setup     "
echo "========================================"

# 1. Check/Install Homebrew
if ! command -v brew &> /dev/null; then
    echo "[!] Homebrew not found. It is required to install audio drivers."
    echo "    Please install Homebrew first: https://brew.sh/"
    read -p "Press Enter to exit..."
    exit 1
fi

# 2. Install Audio Drivers (BlackHole) & PortAudio
echo "[*] Checking Audio Drivers..."
if brew list blackhole-2ch &> /dev/null && brew list blackhole-16ch &> /dev/null; then
    echo "    BlackHole drivers already installed."
else
    echo "    Installing BlackHole drivers..."
    brew install blackhole-2ch blackhole-16ch
    
    # Also install portaudio for PyAudio
    brew install portaudio
    
    echo "    [IMPORTANT] If this is the first time installing BlackHole,"
    echo "    you might need to restart your computer or CoreAudio."
fi

# 3. Python Setup
echo "[*] Setting up Python Environment..."

if [ ! -d "venv" ]; then
    echo "    Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate

echo "[*] Installing Dependencies..."
pip install --upgrade pip > /dev/null
pip install -r requirements.txt

# 4. Launch
echo ""
echo "[*] Launching Application..."
python3 launcher.py
