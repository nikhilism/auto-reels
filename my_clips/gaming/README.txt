Drop your raw gaming clips here.

Supported formats: .mp4, .mov, .avi, .mkv, .webm, .m4v

Then run:
  python clip_studio.py --channel gaming

The system will:
  - Analyze each clip with Gemini Vision (understands racing, shooting, open world etc.)
  - Find the most exciting moment using motion detection
  - Crop to 9:16 portrait automatically
  - Apply color grading based on the content type
  - Apply speed ramp / zoom effects
  - Save processed segments to: processed_clips/gaming/

Once processed, the main reel pipeline will USE THESE CLIPS AUTOMATICALLY
instead of downloading from Pexels.

TIPS:
  - Longer clips (30s+) are better — more moments to choose from
  - High-action moments work best (races, gunfights, stunts)
  - 720p or 1080p quality is fine — no need for 4K
  - Vertical clips (9:16) can also be used — they'll be used as-is
