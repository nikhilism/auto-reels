# Auto Reels 🎬

Automated YouTube Shorts & Instagram Reels generator for 3 channels:
- 🎨 **Drawing** — Art tips, techniques, art history
- 🎮 **Gaming** — GTA 5, Forza Horizon 6 tips, facts & news
- 📚 **Informative** — Mind-blowing facts, science, history

---

## How it works

```
Run main.py
    ↓
Gemini generates a 55-second script + metadata
    ↓
Edge TTS converts it to voiceover (free, local)
    ↓
Pexels downloads a relevant background video (free)
    ↓
Whisper transcribes the audio for word-level timing
    ↓
MoviePy assembles: background + dark overlay + animated captions
    ↓
Final .mp4 saved to output/<channel>/
    ↓ (optional)
YouTube auto-upload (toggle in config.yaml)
```

---

## First-Time Setup

**Requirements:** Python 3.10+, FFmpeg

### 1. Install FFmpeg (required for video processing)
Download from https://ffmpeg.org/download.html and add to your PATH.

Or on Windows with winget:
```
winget install ffmpeg
```

### 2. Run the setup script
```bash
python setup.py
```
This will:
- Create all directories
- Copy `.env.example` → `.env`
- Download the Montserrat Bold caption font
- Install all Python dependencies

### 3. Add your API keys to `.env`
```
GEMINI_API_KEY=your_key_here
PEXELS_API_KEY=your_key_here
```

- Get Gemini key free at: https://aistudio.google.com
- Get Pexels key free at: https://www.pexels.com/api/

---

## Usage

```bash
# Test script generation only (no video render, fast)
python main.py --dry-run

# Test a single channel
python main.py --channel gaming --dry-run

# Generate one reel for the gaming channel
python main.py --channel gaming

# Generate reels for ALL channels
python main.py

# Use a custom config file
python main.py --config my_config.yaml
```

---

## Configuration

All settings are in `config.yaml` — no code changes needed.

### Enable/disable a channel
```yaml
channels:
  gaming:
    enabled: false  # Set to true/false
```

### Change topics
```yaml
channels:
  gaming:
    topics:
      - "GTA 5 hidden secrets"
      - "Forza Horizon 6 best cars"
      - "your custom topic here"
```

### Enable auto-upload to YouTube
```yaml
channels:
  gaming:
    auto_upload: true  # Default: false
```
> First time: run `python src/uploader.py` to complete YouTube OAuth2 setup.

### Switch to a different TTS voice
```yaml
channels:
  drawing:
    tts_voice: "en-GB-SoniaNeural"  # Any Edge TTS voice name
    tts_rate: "+10%"
```
See all available voices: `python -c "from src.tts_generator import list_available_voices; list_available_voices()"`

### Customize captions
```yaml
channels:
  informative:
    caption_style:
      font_size: 80
      font_color: "#FFFFFF"
      highlight_color: "#00CFFF"  # Color of the currently-spoken word
      stroke_color: "#000000"
      stroke_width: 3
      max_words_per_line: 3       # 2-4 recommended
```

---

## Output

Rendered videos are saved to:
```
output/
├── drawing/    ← Drawing channel reels
├── gaming/     ← Gaming channel reels
└── informative/← Informative channel reels
```

Each file is named: `YYYYMMDD_HHMMSS_<title>.mp4`

---

## Enabling Auto-Upload (Optional)

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a project → Enable **YouTube Data API v3**
3. Create **OAuth 2.0 Client ID** credentials (Desktop app type)
4. Download the JSON file and rename it to `client_secrets.json`
5. Add to `.env`: `YOUTUBE_CLIENT_SECRETS_FILE=client_secrets.json`
6. Run once to authenticate: `python src/uploader.py`
7. Set `auto_upload: true` in `config.yaml` for your channel

---

## Security

- API keys are stored in `.env` — **never in code**
- `.env` is in `.gitignore` — will **never** be committed to git
- `client_secrets.json` and `.youtube_token.pickle` are also gitignored

---

## Upgrading TTS to ElevenLabs (Later)

When you're ready for premium voices, edit `src/tts_generator.py` to add ElevenLabs support, and add `ELEVENLABS_API_KEY` to your `.env`. The rest of the pipeline stays the same.
