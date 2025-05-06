# Link2Wave

Link2Wave is a multi-purpose audio tool that combines:
1. YouTube audio ripper and stem separator
2. A web-based vocal recording booth with live effects
3. Audio processing with pitch shifting and autotune

## Features

### YouTube Audio Ripper
- Download high-quality audio from YouTube videos
- Convert to MP3 or WAV format
- Separate audio into stems (vocals, drums, bass, other) using Demucs AI
- Access all downloaded audio in your Music/YT-Rips folder

### Stem Separation
- Powered by Demucs AI for high-quality stem separation
- Extract vocals, drums, bass, and other instruments
- Download or play individual stems directly in the browser
- Process your own audio files

### Vocal Booth
- Record audio from your microphone with live effects
- Apply EQ, reverb, delay, and compression in real-time
- Save recordings as WAV or MP3 files
- Convert between audio formats

### Audio Processing
- Apply pitch shifting to change the pitch of your audio
- Use autotune to correct vocal pitch to musical notes
- Adjust autotune strength for subtle to extreme effects
- Preview processed audio directly in the browser

## Installation

### Prerequisites
- Python 3.9+ 
- FFmpeg (must be installed and in your PATH)
- 2GB+ RAM for stem separation
- CUDA-compatible GPU (optional, for faster stem separation)

```bash
# Clone the repository
git clone https://github.com/yourusername/link2wave.git
cd link2wave

# Create a virtual environment
# On macOS/Linux:
python -m venv .venv
source .venv/bin/activate

# On Windows:
python -m venv .venv
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Usage

### Web Interface

The web interface provides a complete audio workstation in your browser:

```bash
# Start the web server
# On macOS/Linux:
python link2wave_web.py

# On Windows:
python link2wave_web.py
```

Then open http://localhost:8080 in your browser.

### Command-line Interface

Link2Wave can also be used from the command line:

```bash
# Download audio from YouTube
python link2wave.py rip "https://www.youtube.com/watch?v=EXAMPLE" --format mp3

# Separate audio into stems
python link2wave.py separate /path/to/audio.mp3

# Play a stem
python link2wave.py play /path/to/stem.wav

# Apply pitch shifting
python link2wave.py pitch /path/to/audio.wav --amount 2

# Apply autotune
python link2wave.py autotune /path/to/audio.wav --strength 5

# Interactive mode
python link2wave.py -i
```

## Testing on Windows or Mac

### Windows
1. Install Python 3.9+ from the [official website](https://www.python.org/downloads/windows/)
2. Install FFmpeg:
   - Download the latest build from [FFmpeg.org](https://ffmpeg.org/download.html#build-windows)
   - Extract the ZIP file and add the `bin` folder to your PATH environment variable
3. Follow the installation instructions above
4. Launch the web interface by running `python link2wave_web.py`
5. Check that your microphone is properly configured in Windows settings
6. Access the web interface at http://localhost:8080

### macOS
1. Install Python 3.9+ from the [official website](https://www.python.org/downloads/mac-osx/)
2. Install FFmpeg using Homebrew:
   ```bash
   brew install ffmpeg
   ```
3. Follow the installation instructions above
4. Launch the web interface by running `python link2wave_web.py`
5. Check that your microphone access is allowed in System Preferences > Security & Privacy > Microphone
6. Access the web interface at http://localhost:8080

## Troubleshooting

### Common Issues
- **FFmpeg not found**: Ensure FFmpeg is installed and in your PATH
- **Microphone access denied**: Allow browser access to your microphone
- **Stem separation is slow**: For faster processing, use a CUDA-compatible GPU
- **Audio playback issues**: Try using headphones to avoid feedback loops

### Dependencies
If you encounter missing dependencies, ensure you've activated your virtual environment and installed all requirements:
```bash
# On macOS/Linux:
source .venv/bin/activate

# On Windows:
.venv\Scripts\activate

pip install -r requirements.txt
```

## License

MIT 
