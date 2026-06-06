"""
clip_studio.py
──────────────
Standalone tool to process your own gaming/drawing/informative clips
into short-form-ready vertical segments with cinematic effects.

HOW TO USE:
  1. Drop your raw clips into:
       my_clips/gaming/        ← for the gaming channel
       my_clips/drawing/       ← for the drawing channel
       my_clips/informative/   ← for the informative channel

  2. Run:
       python clip_studio.py --channel gaming

  3. Processed clips are saved to:
       processed_clips/gaming/

  4. The main reel pipeline will automatically use these
     instead of downloading from Pexels.

COMMANDS:
  python clip_studio.py --channel gaming           # Process all clips
  python clip_studio.py --channel gaming --analyze # Analyze only (no edits)
  python clip_studio.py --channel gaming --clip myclip.mp4  # Single clip

WHAT IT DOES TO EACH CLIP:
  - Gemini Vision analyzes content (racing? shooter? open world?)
  - Motion detection finds the most exciting moment
  - Extracts best 12-15 second segment
  - Crops to 9:16 portrait with smart centering
  - Applies color grade based on detected content type
  - Optional speed ramp around the peak action moment
  - Outputs ready-to-use .mp4 for the reel pipeline
"""

import argparse
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from PIL import Image as _PIL
if not hasattr(_PIL, "ANTIALIAS"):
    _PIL.ANTIALIAS = _PIL.LANCZOS

load_dotenv()
sys.path.insert(0, os.path.dirname(__file__))

from src.clip_analyzer import analyze_clip, AnalysisResult
from src.clip_effects import process_clip

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("clip_studio.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("clip_studio")

SUPPORTED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}

CHANNEL_FOLDERS = {
    "gaming":     ("my_clips/gaming",     "processed_clips/gaming"),
    "drawing":    ("my_clips/drawing",    "processed_clips/drawing"),
    "informative": ("my_clips/informative", "processed_clips/informative"),
}


def scan_clips(folder: str) -> list[Path]:
    """Find all video files in a folder."""
    folder_path = Path(folder)
    if not folder_path.exists():
        folder_path.mkdir(parents=True, exist_ok=True)
        logger.warning(f"Created empty clips folder: {folder}")
        logger.info(f"Drop your video clips there, then run again.")
        return []

    clips = [
        p for p in folder_path.iterdir()
        if p.suffix.lower() in SUPPORTED_EXTENSIONS and p.is_file()
    ]
    clips.sort(key=lambda p: p.stat().st_size, reverse=True)  # largest first
    return clips


def process_channel(
    channel_id: str,
    analyze_only: bool = False,
    specific_clip: str = None,
    clips_per_video: int = 4,
) -> None:
    """Process all clips for a channel."""
    if channel_id not in CHANNEL_FOLDERS:
        logger.error(f"Unknown channel '{channel_id}'. Valid: {list(CHANNEL_FOLDERS)}")
        sys.exit(1)

    input_folder, output_folder = CHANNEL_FOLDERS[channel_id]
    os.makedirs(output_folder, exist_ok=True)

    if specific_clip:
        clips = [Path(specific_clip)]
    else:
        clips = scan_clips(input_folder)

    if not clips:
        logger.warning(f"No clips found in {input_folder}/")
        logger.info(
            f"Supported formats: {', '.join(SUPPORTED_EXTENSIONS)}\n"
            f"Drop your files there and re-run."
        )
        return

    logger.info(f"Found {len(clips)} clip(s) in {input_folder}/")
    logger.info(f"Output -> {output_folder}/")

    processed = []
    errors = []

    for i, clip_path in enumerate(clips):
        logger.info(f"\n{'='*60}")
        logger.info(f"  [{i+1}/{len(clips)}] {clip_path.name}")
        logger.info(f"{'='*60}")

        try:
            # Step 1: Analyze the clip with Gemini Vision
            logger.info("Analyzing clip content (Gemini Vision)...")
            analysis = analyze_clip(str(clip_path), channel_id)
            _print_analysis(analysis, clip_path.name)

            if analyze_only:
                continue

            # Step 2: Process — extract highlights, apply effects, crop to 9:16
            logger.info("Applying effects and cropping to 9:16...")
            output_paths = process_clip(
                clip_path=str(clip_path),
                analysis=analysis,
                output_dir=output_folder,
                num_segments=min(clips_per_video, max(1, clips_per_video // len(clips))),
            )

            for op in output_paths:
                size_mb = os.path.getsize(op) / (1024 * 1024)
                logger.info(f"  Saved: {os.path.basename(op)} ({size_mb:.1f} MB)")
                processed.append(op)

        except Exception as e:
            logger.error(f"Failed to process {clip_path.name}: {e}", exc_info=True)
            errors.append((clip_path.name, str(e)))

    # Summary
    logger.info(f"\n{'='*60}")
    if analyze_only:
        logger.info(f"Analysis complete for {len(clips)} clip(s).")
    else:
        logger.info(f"Done! {len(processed)} clip segment(s) ready in {output_folder}/")
        logger.info("The reel pipeline will use these automatically.")
        if errors:
            logger.warning(f"{len(errors)} clip(s) had errors:")
            for name, err in errors:
                logger.warning(f"  - {name}: {err}")
    logger.info(f"{'='*60}")


def _print_analysis(result: "AnalysisResult", filename: str) -> None:
    print(f"\n  File    : {filename}")
    print(f"  Type    : {result.content_type}")
    print(f"  Score   : {result.excitement_score}/10")
    print(f"  Peak    : {result.peak_moment:.1f}s (most exciting moment)")
    print(f"  Grade   : {result.color_grade}")
    print(f"  Effects : {', '.join(result.effects)}")
    print(f"  Summary : {result.description}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Clip Studio — Edit your own clips into reel-ready vertical segments"
    )
    parser.add_argument("--channel", required=True, help="gaming / drawing / informative")
    parser.add_argument("--analyze", action="store_true", help="Analyze only, no edits")
    parser.add_argument("--clip", help="Process a single specific clip file")
    parser.add_argument(
        "--count", type=int, default=4,
        help="How many processed segments to generate in total (default: 4)"
    )
    args = parser.parse_args()

    process_channel(
        channel_id=args.channel,
        analyze_only=args.analyze,
        specific_clip=args.clip,
        clips_per_video=args.count,
    )


if __name__ == "__main__":
    main()
