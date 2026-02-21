# Live Translation Bridge (BETA)

Real-time, bidirectional voice-to-voice translation for macOS. This tool captures audio from your meetings (Zoom, Google Meet, etc.), translates it instantly, and plays it back using ultra-low latency AI voices.

## 🚀 Features
- **Low Latency**: Optimized pipeline using Deepgram (STT), Groq (Translation), and Cartesia (TTS).
- **Bidirectional**: Designed for English <-> Spanish conversations.
- **Easy Launcher**: Interactive menu to manage API keys and monitor audio devices.

## 📋 Prerequisites
This project is currently optimized for **macOS**.
1. **BlackHole 2ch**: Required for audio routing. Install it via [Existential Audio](https://existential.audio/blackhole/).
2. **Audio Setup**: You need to create a **Multi-Output Device** in your "Audio MIDI Setup" including your headphones and BlackHole 2ch.

## ⚙️ Installation & Setup
1. **Clone the repository**:
   ```bash
   git clone https://github.com/dende190/traducciones_tiempo_real.git
   cd traducciones_tiempo_real
   ```
2. **Install dependencies**:
   Everything is automated! You can simply run:
   ```bash
   ./install_and_run.command
   ```
   Or manually:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

## 🛠️ How to Start
Simply run the interactive launcher:
```bash
python launcher.py
```
On first run, it will prompt you for your API Keys:
- `DEEPGRAM_API_KEY`
- `GROQ_API_KEY`
- `CARTESIA_API_KEY`

## 🎧 Audio Configuration (Important)
Follow the [Detailed Setup Guide](setup_guide.md) to configure your system audio correctly so the script can "hear" your meetings.

---
*Developed by [Dende](https://github.com/dende190)*
