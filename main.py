"""
main.py
───────
Orchestrator for the Auto Reels pipeline.

Usage:
  python main.py                          # Process all enabled channels
  python main.py --channel gaming         # Process a single channel
  python main.py --channel gaming --dry-run  # Generate script only, no video render

Each run produces one reel per enabled channel in the output/ directory.
"""

import argparse
import logging
import os
import sys
import yaml
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# ── Load .env first, before any module that needs keys ────────────────────────
load_dotenv()

# ── Pillow 10+ compatibility fix for MoviePy 1.0.3 ───────────────────────────
# PIL removed Image.ANTIALIAS in v10.0.0 (renamed to LANCZOS).
# MoviePy 1.0.3 still references the old name — this patches it before import.
from PIL import Image as _PILImage
if not hasattr(_PILImage, "ANTIALIAS"):
    _PILImage.ANTIALIAS = _PILImage.LANCZOS

# ── Import pipeline modules ───────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))
from src.script_generator import generate_script
from src.tts_generator import generate_voiceover
from src.asset_fetcher import fetch_multiple_clips
from src.caption_generator import get_word_timestamps, group_into_caption_chunks
from src.video_editor import assemble_video
from src.music_fetcher import fetch_background_music
from src.uploader import upload_to_youtube
from src.settings_reader import load_settings

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("auto_reels.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("main")


def load_config(config_path: str = "config.yaml") -> dict:
    """Load and return the YAML config."""
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def make_temp_paths(channel_id: str) -> dict:
    """Build temp file paths for a single pipeline run."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = f"temp/{channel_id}_{ts}"
    clips_dir = f"{base}_clips"
    os.makedirs(clips_dir, exist_ok=True)
    return {
        "audio": f"{base}_voiceover.mp3",
        "clips_dir": clips_dir,
        "music": f"{base}_music.mp3",
    }


def make_output_path(channel_cfg: dict, title: str) -> str:
    """Build the output .mp4 file path."""
    out_dir = channel_cfg["output_dir"]
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_title = "".join(c if c.isalnum() or c in " _-" else "_" for c in title)[:50]
    return f"{out_dir}/{ts}_{safe_title}.mp4"


def _find_own_clips(folder: str) -> list[str]:
    """
    Find all processed video clips in a folder (from clip_studio.py output).
    Returns sorted list of .mp4 paths, empty list if folder doesn't exist or is empty.
    """
    if not os.path.exists(folder):
        return []
    exts = {".mp4", ".mov", ".avi", ".mkv"}
    clips = [
        os.path.join(folder, f)
        for f in sorted(os.listdir(folder))
        if os.path.splitext(f)[1].lower() in exts
    ]
    return clips


def run_channel(
    channel_id: str,
    channel_cfg: dict,
    global_cfg: dict,
    dry_run: bool = False,
    topic_override: str = None,
) -> None:
    """
    Run the full pipeline for a single channel.

    Args:
        channel_id     : Key from config (e.g., "gaming").
        channel_cfg    : Channel-specific config dict.
        global_cfg     : Global config dict.
        dry_run        : If True, only generate and print the script.
        topic_override : Topic from settings.txt (overrides random selection).
    """
    logger.info(f"{'='*60}")
    logger.info(f"  CHANNEL: {channel_cfg['name']}")
    logger.info(f"{'='*60}")

    # ── Step 1: Generate Script ────────────────────────────────────────────────
    logger.info("Step 1/6 -- Generating script...")
    if topic_override:
        logger.info(f"Using topic from settings.txt: '{topic_override}'")
    # Pass channel_id so script_generator can pick right fallback queries
    channel_cfg["channel_id"] = channel_id
    script_data = generate_script(channel_cfg, topic_override=topic_override)

    print(f"\n{'─'*50}")
    print(f"TITLE: {script_data['title']}")
    print(f"\nSCRIPT:\n{script_data['script']}")
    print(f"\nPEXELS QUERIES: {script_data['pexels_queries']}")
    print(f"{'─'*50}\n")

    if dry_run:
        logger.info("Dry run complete — skipping video render.")
        return

    temp = make_temp_paths(channel_id)
    os.makedirs("temp", exist_ok=True)

    # ── Step 2: Generate Voiceover ────────────────────────────────────────────────
    logger.info("Step 2/6 -- Generating voiceover (Edge TTS)...")
    generate_voiceover(
        script=script_data["script"],
        output_path=temp["audio"],
        voice=channel_cfg.get("tts_voice", "en-US-AriaNeural"),
        rate=channel_cfg.get("tts_rate", "+5%"),
        pitch=channel_cfg.get("tts_pitch", "+0Hz"),
    )

    # ── Step 3: Get Background Clips ─────────────────────────────────────────
    # Priority: processed_clips/<channel>/ (your own clips) → Pexels (fallback)
    processed_clips_dir = f"processed_clips/{channel_id}"
    own_clips = _find_own_clips(processed_clips_dir)

    if own_clips:
        logger.info(
            f"Step 3/6 -- Using YOUR clips from {processed_clips_dir}/ "
            f"({len(own_clips)} available)"
        )
        # Pick 4 clips, cycling through available ones
        import random
        clip_paths = (own_clips * 4)[:4]
        random.shuffle(clip_paths)
        logger.info(f"Selected: {[os.path.basename(p) for p in clip_paths]}")
    else:
        logger.info("Step 3/6 -- Fetching background clips (Pexels)...")
        logger.info(
            f"  Tip: Run 'clip_studio.py --channel {channel_id}' with your own "
            f"clips in my_clips/{channel_id}/ to use them instead."
        )
        all_queries = script_data["pexels_queries"] + channel_cfg.get("pexels_keywords", [])
        clip_paths = fetch_multiple_clips(
            queries=all_queries,
            output_dir=temp["clips_dir"],
            count=4,
            min_duration=12,
        )
    logger.info(f"Using {len(clip_paths)} background clip(s).")

    # ── Step 4: Fetch Background Music ──────────────────────────────────────
    logger.info("Step 4/6 -- Fetching background music (Jamendo/CDN)...")
    music_path = fetch_background_music(
        channel_id=channel_id,
        output_path=temp["music"],
    )

    # ── Step 5: Generate Captions ────────────────────────────────────────────
    logger.info("Step 5/6 -- Generating captions (Whisper)...")
    words = get_word_timestamps(
        audio_path=temp["audio"],
        model_size=global_cfg.get("whisper_model", "base"),
    )
    caption_chunks = group_into_caption_chunks(
        words=words,
        max_words=channel_cfg.get("caption_style", {}).get("max_words_per_line", 3),
    )

    # ── Step 6: Assemble Video ────────────────────────────────────────────────
    logger.info("Step 6/6 -- Assembling final video (MoviePy)...")
    output_path = make_output_path(channel_cfg, script_data["title"])
    assemble_video(
        clip_paths=clip_paths,
        audio_path=temp["audio"],
        caption_chunks=caption_chunks,
        output_path=output_path,
        channel_cfg=channel_cfg,
        global_cfg=global_cfg,
    )

    logger.info(f"Done! Reel ready for review: {output_path}")
    print(f"\n{'='*60}")
    print(f"  Done! Reel saved to:")
    print(f"     {output_path}")
    print(f"{'='*60}\n")

    # ── Optional: Auto Upload ─────────────────────────────────────────────────
    if channel_cfg.get("auto_upload", False):
        logger.info("Auto-upload enabled -- uploading to YouTube...")
        try:
            upload_to_youtube(
                video_path=output_path,
                title=script_data["title"],
                description=script_data["description"],
                hashtags=script_data["hashtags"],
                channel_name=channel_cfg["name"],
                privacy="private",  # Upload as private for safety; change manually to public
            )
        except Exception as e:
            logger.error(f"Upload failed: {e}")
    else:
        logger.info(
            "Auto-upload is OFF. Review the video, then upload manually.\n"
            "To enable: set 'auto_upload: true' in config.yaml for this channel."
        )


def main():
    parser = argparse.ArgumentParser(
        description="Auto Reels — Generate daily YouTube Shorts / Instagram Reels"
    )
    parser.add_argument(
        "--channel",
        help="Process a specific channel only (e.g., 'gaming'). Default: all enabled.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate script only — do not render video.",
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to config file (default: config.yaml).",
    )
    args = parser.parse_args()

    cfg = load_config(args.config)
    channels = cfg.get("channels", {})
    global_cfg = cfg.get("global", {})

    # ── Load user settings.txt ────────────────────────────────────────────────
    user_settings = load_settings()
    logger.info("Loaded settings.txt")

    # Filter to specific channel if requested via CLI
    if args.channel:
        if args.channel not in channels:
            logger.error(
                f"Channel '{args.channel}' not found in config. "
                f"Available: {list(channels.keys())}"
            )
            sys.exit(1)
        channels = {args.channel: channels[args.channel]}

    # Apply enabled flags from settings.txt (CLI --channel overrides this)
    if not args.channel:
        channels = {
            k: v for k, v in channels.items()
            if user_settings["enabled"].get(k, True) and v.get("enabled", True)
        }
    else:
        channels = {k: v for k, v in channels.items() if v.get("enabled", True)}

    if not channels:
        logger.warning("No enabled channels found. Check settings.txt and config.yaml.")
        sys.exit(0)

    logger.info(f"Running pipeline for channels: {list(channels.keys())}")

    errors = []
    for channel_id, channel_cfg in channels.items():
        # Apply highlight color override from settings.txt
        color = user_settings["highlight_colors"].get(channel_id)
        if color:
            channel_cfg.setdefault("caption_style", {})["highlight_color"] = color

        # Apply auto_upload override from settings.txt
        if user_settings["auto_upload"].get(channel_id):
            channel_cfg["auto_upload"] = True

        # Get topic override from settings.txt
        topic = user_settings["topics"].get(channel_id)

        try:
            run_channel(
                channel_id=channel_id,
                channel_cfg=channel_cfg,
                global_cfg=global_cfg,
                dry_run=args.dry_run,
                topic_override=topic,
            )
        except Exception as e:
            logger.error(f"Pipeline failed for channel '{channel_id}': {e}", exc_info=True)
            errors.append((channel_id, str(e)))

    if errors:
        print(f"\n  {len(errors)} channel(s) had errors:")
        for ch, err in errors:
            print(f"   - {ch}: {err}")
    else:
        print("\nAll channels processed successfully!")


if __name__ == "__main__":
    main()
