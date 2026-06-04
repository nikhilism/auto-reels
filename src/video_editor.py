"""
video_editor.py
───────────────
Assembles the final vertical reel/short using MoviePy.

Steps:
  1. Load background video, crop to 9:16, trim to audio length.
  2. Add a dark overlay for caption readability.
  3. Overlay the voiceover audio.
  4. Render animated captions with per-word highlighting.
  5. Export the final .mp4.
"""

import logging
import os
import textwrap
from PIL import Image, ImageDraw, ImageFont
import numpy as np

# ── Pillow 10+ compatibility fix for MoviePy 1.0.3 ───────────────────────────
if not hasattr(Image, "ANTIALIAS"):
    Image.ANTIALIAS = Image.LANCZOS

from moviepy.editor import (
    VideoFileClip,
    AudioFileClip,
    CompositeVideoClip,
    ColorClip,
    ImageClip,
)

logger = logging.getLogger(__name__)

# ── Default settings (overridden by channel config) ───────────────────────────
DEFAULT_W = 1080
DEFAULT_H = 1920
DEFAULT_FONT_SIZE = 76
DEFAULT_FONT_COLOR = "#FFFFFF"
DEFAULT_HIGHLIGHT_COLOR = "#FFD700"
DEFAULT_STROKE_COLOR = "#000000"
DEFAULT_STROKE_WIDTH = 3
DEFAULT_MAX_WORDS = 3
DEFAULT_FONT_PATH = "assets/fonts/Montserrat-Bold.ttf"


def hex_to_rgb(hex_color: str) -> tuple:
    """Convert '#RRGGBB' to (R, G, B) tuple."""
    h = hex_color.lstrip("#")
    return tuple(int(h[i: i + 2], 16) for i in (0, 2, 4))


def _load_font(font_path: str, size: int) -> ImageFont.FreeTypeFont:
    """Load a TTF font, fall back to default if not found."""
    if os.path.exists(font_path):
        return ImageFont.truetype(font_path, size)
    logger.warning(f"Font not found: {font_path}. Using PIL default font.")
    try:
        # Try a system font on Windows
        return ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", size)
    except Exception:
        return ImageFont.load_default()


def _render_caption_frame(
    chunk: dict,
    current_word_idx: int,
    width: int,
    height: int,
    font_path: str,
    font_size: int,
    font_color: str,
    highlight_color: str,
    stroke_color: str,
    stroke_width: int,
    max_words_per_line: int,
) -> np.ndarray:
    """
    Render a single caption frame as an RGBA numpy array.
    The current word is highlighted; others are in font_color.
    """
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = _load_font(font_path, font_size)

    words_in_chunk = chunk["words"]
    line_words = [w["word"] for w in words_in_chunk]

    # Break into lines
    lines = []
    for i in range(0, len(line_words), max_words_per_line):
        lines.append(line_words[i: i + max_words_per_line])

    # Measure total text block height
    line_height = font_size + 16
    total_height = line_height * len(lines)
    start_y = (height // 2) - (total_height // 2)

    word_global_idx = 0
    for line in lines:
        # Measure total line width for centering
        word_sizes = []
        for w in line:
            bbox = draw.textbbox((0, 0), w + " ", font=font)
            word_sizes.append((bbox[2] - bbox[0], bbox[3] - bbox[1]))

        total_line_w = sum(ws[0] for ws in word_sizes)
        x = (width - total_line_w) // 2
        y = start_y

        for i, w in enumerate(line):
            is_current = word_global_idx == current_word_idx
            color = hex_to_rgb(highlight_color) if is_current else hex_to_rgb(font_color)
            stroke_clr = hex_to_rgb(stroke_color)

            # Draw stroke (outline)
            for dx in range(-stroke_width, stroke_width + 1):
                for dy in range(-stroke_width, stroke_width + 1):
                    if dx != 0 or dy != 0:
                        draw.text((x + dx, y + dy), w, font=font, fill=stroke_clr + (255,))

            # Draw word
            draw.text((x, y), w, font=font, fill=color + (255,))
            x += word_sizes[i][0]
            word_global_idx += 1

        start_y += line_height

    return np.array(img)


def _make_caption_clips(
    caption_chunks: list[dict],
    total_duration: float,
    width: int,
    height: int,
    style: dict,
    font_path: str,
) -> list:
    """
    Build a list of MoviePy ImageClips — one per word highlight state.
    """
    clips = []
    font_size = style.get("font_size", DEFAULT_FONT_SIZE)
    font_color = style.get("font_color", DEFAULT_FONT_COLOR)
    highlight_color = style.get("highlight_color", DEFAULT_HIGHLIGHT_COLOR)
    stroke_color = style.get("stroke_color", DEFAULT_STROKE_COLOR)
    stroke_width = style.get("stroke_width", DEFAULT_STROKE_WIDTH)
    max_words = style.get("max_words_per_line", DEFAULT_MAX_WORDS)

    for chunk in caption_chunks:
        words = chunk["words"]
        for word_idx, word in enumerate(words):
            word_start = word["start"]
            word_end = word["end"]
            duration = word_end - word_start
            if duration <= 0:
                continue

            # Cap to total video duration
            if word_start >= total_duration:
                break

            frame = _render_caption_frame(
                chunk=chunk,
                current_word_idx=word_idx,
                width=width,
                height=height,
                font_path=font_path,
                font_size=font_size,
                font_color=font_color,
                highlight_color=highlight_color,
                stroke_color=stroke_color,
                stroke_width=stroke_width,
                max_words_per_line=max_words,
            )

            clip = (
                ImageClip(frame, ismask=False)
                .set_start(word_start)
                .set_duration(min(duration, total_duration - word_start))
            )
            clips.append(clip)

    return clips


def assemble_video(
    background_video_path: str,
    audio_path: str,
    caption_chunks: list[dict],
    output_path: str,
    channel_cfg: dict,
    global_cfg: dict,
) -> str:
    """
    Assemble the final reel video.

    Args:
        background_video_path : Path to the background .mp4 clip.
        audio_path            : Path to the TTS .mp3 voiceover.
        caption_chunks        : Output of caption_generator.group_into_caption_chunks().
        output_path           : Where to write the final .mp4.
        channel_cfg           : Channel config dict.
        global_cfg            : Global config dict.

    Returns:
        Path to the rendered video.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    W = global_cfg.get("video_width", DEFAULT_W)
    H = global_cfg.get("video_height", DEFAULT_H)
    font_path = global_cfg.get("font_path", DEFAULT_FONT_PATH)
    caption_style = channel_cfg.get("caption_style", {})

    logger.info("Loading audio...")
    audio = AudioFileClip(audio_path)
    total_duration = audio.duration
    logger.info(f"Audio duration: {total_duration:.2f}s")

    logger.info("Loading and processing background video...")
    bg = VideoFileClip(background_video_path, audio=False)

    # ── Crop to 9:16 ──────────────────────────────────────────────────────────
    # Resize so that the smaller dimension fills the target, then center-crop
    bg_aspect = bg.w / bg.h
    target_aspect = W / H

    if bg_aspect > target_aspect:
        # Video is wider than target — scale by height
        bg = bg.resize(height=H)
    else:
        # Video is taller/narrower than target — scale by width
        bg = bg.resize(width=W)

    # Center crop
    x_center = bg.w / 2
    y_center = bg.h / 2
    bg = bg.crop(
        x1=x_center - W / 2,
        y1=y_center - H / 2,
        x2=x_center + W / 2,
        y2=y_center + H / 2,
    )

    # ── Loop or trim to audio duration ────────────────────────────────────────
    if bg.duration < total_duration:
        loops = int(total_duration / bg.duration) + 1
        from moviepy.editor import concatenate_videoclips
        bg = concatenate_videoclips([bg] * loops)

    bg = bg.subclip(0, total_duration)

    # ── Dark overlay for caption readability ──────────────────────────────────
    overlay = ColorClip(size=(W, H), color=(0, 0, 0)).set_opacity(0.45)
    overlay = overlay.set_duration(total_duration)

    # ── Caption clips ─────────────────────────────────────────────────────────
    logger.info("Rendering caption clips...")
    caption_clips = _make_caption_clips(
        caption_chunks=caption_chunks,
        total_duration=total_duration,
        width=W,
        height=H,
        style=caption_style,
        font_path=font_path,
    )

    # ── Composite ─────────────────────────────────────────────────────────────
    logger.info("Compositing final video...")
    all_clips = [bg, overlay] + caption_clips
    final = CompositeVideoClip(all_clips, size=(W, H))
    final = final.set_audio(audio)
    final = final.set_duration(total_duration)

    # ── Export ────────────────────────────────────────────────────────────────
    logger.info(f"Exporting → {output_path}")
    final.write_videofile(
        output_path,
        fps=30,
        codec="libx264",
        audio_codec="aac",
        temp_audiofile="temp/temp_audio.m4a",
        remove_temp=True,
        logger=None,  # suppress verbose MoviePy bar
        threads=4,
    )

    # Cleanup
    audio.close()
    bg.close()
    final.close()

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    logger.info(f"✅ Video exported ({size_mb:.1f} MB): {output_path}")
    return output_path
