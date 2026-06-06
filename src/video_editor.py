"""
video_editor.py
───────────────
Assembles the final vertical reel/short using MoviePy.

Steps:
  1. Load 3-4 background clips, crop each to 9:16, distribute evenly.
  2. Apply crossfade transitions between clips.
  3. Add dark overlay for caption readability.
  4. Overlay the TTS voiceover.
  5. Mix royalty-free background music at 20% volume.
  6. Render animated word-by-word captions.
  7. Export final .mp4 at 1080x1920.
"""

import logging
import os
from PIL import Image, ImageDraw, ImageFont
import numpy as np

# ── Pillow 10+ compatibility fix for MoviePy 1.0.3 ───────────────────────────
if not hasattr(Image, "ANTIALIAS"):
    Image.ANTIALIAS = Image.LANCZOS

from moviepy.editor import (
    VideoFileClip,
    AudioFileClip,
    CompositeVideoClip,
    CompositeAudioClip,
    ColorClip,
    ImageClip,
    concatenate_videoclips,
    concatenate_audioclips,
)

logger = logging.getLogger(__name__)

# ── Defaults (overridden by channel config) ───────────────────────────────────
DEFAULT_W = 1080
DEFAULT_H = 1920
DEFAULT_FONT_SIZE = 76
DEFAULT_FONT_COLOR = "#FFFFFF"
DEFAULT_HIGHLIGHT_COLOR = "#FFD700"
DEFAULT_STROKE_COLOR = "#000000"
DEFAULT_STROKE_WIDTH = 3
DEFAULT_MAX_WORDS = 3
DEFAULT_FONT_PATH = "assets/fonts/Montserrat-Bold.ttf"
CROSSFADE_DURATION = 0.5   # seconds between clips
MUSIC_VOLUME = 0.18        # 18% — just under 20%


def hex_to_rgb(hex_color: str) -> tuple:
    h = hex_color.lstrip("#")
    return tuple(int(h[i: i + 2], 16) for i in (0, 2, 4))


def _load_font(font_path: str, size: int) -> ImageFont.FreeTypeFont:
    if os.path.exists(font_path):
        return ImageFont.truetype(font_path, size)
    logger.warning(f"Font not found: {font_path}. Trying system font.")
    try:
        return ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", size)
    except Exception:
        return ImageFont.load_default()


def _crop_to_vertical(clip: VideoFileClip, W: int, H: int) -> VideoFileClip:
    """Resize and center-crop a clip to exact W x H (9:16)."""
    bg_aspect = clip.w / clip.h
    target_aspect = W / H

    if bg_aspect > target_aspect:
        clip = clip.resize(height=H)
    else:
        clip = clip.resize(width=W)

    x_center = clip.w / 2
    y_center = clip.h / 2
    return clip.crop(
        x1=x_center - W / 2,
        y1=y_center - H / 2,
        x2=x_center + W / 2,
        y2=y_center + H / 2,
    )


def _prepare_clip(clip: VideoFileClip, target_duration: float, W: int, H: int) -> VideoFileClip:
    """Crop to 9:16, loop if needed, trim to target_duration."""
    clip = _crop_to_vertical(clip, W, H)

    # Loop if clip is shorter than target
    if clip.duration < target_duration + 0.5:
        loops = int((target_duration + 1) / clip.duration) + 1
        clip = concatenate_videoclips([clip] * loops)

    return clip.subclip(0, target_duration)


def _build_background(
    clip_paths: list[str],
    total_duration: float,
    W: int,
    H: int,
) -> VideoFileClip:
    """
    Load all clips, give each an equal share of the total duration,
    and concatenate with crossfade transitions.
    """
    n = len(clip_paths)
    # Each clip gets equal time; add crossfade buffer so overlaps work
    clip_duration = (total_duration + (n - 1) * CROSSFADE_DURATION) / n

    logger.info(
        f"Splitting {total_duration:.1f}s across {n} clips "
        f"({clip_duration:.1f}s each, {CROSSFADE_DURATION}s crossfade)"
    )

    prepared = []
    for i, path in enumerate(clip_paths):
        clip = VideoFileClip(path, audio=False)
        clip = _prepare_clip(clip, clip_duration, W, H)
        # Add crossfade-in on all clips except the first
        if i > 0:
            clip = clip.crossfadein(CROSSFADE_DURATION)
        prepared.append(clip)

    if len(prepared) == 1:
        return prepared[0]

    bg = concatenate_videoclips(
        prepared,
        method="compose",
        padding=-CROSSFADE_DURATION,
    )

    # Ensure exact length
    return bg.subclip(0, min(total_duration, bg.duration))


def _render_caption_frame(
    chunk: dict,
    current_word_idx: int,
    W: int,
    H: int,
    font_path: str,
    font_size: int,
    font_color: str,
    highlight_color: str,
    stroke_color: str,
    stroke_width: int,
    max_words_per_line: int,
) -> np.ndarray:
    """Render one caption frame as an RGBA numpy array with word highlighting."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = _load_font(font_path, font_size)

    words_in_chunk = chunk["words"]
    line_words = [w["word"] for w in words_in_chunk]

    lines = []
    for i in range(0, len(line_words), max_words_per_line):
        lines.append(line_words[i: i + max_words_per_line])

    line_height = font_size + 18
    total_text_h = line_height * len(lines)

    # Position captions in the lower-middle (80% down)
    start_y = int(H * 0.78) - total_text_h // 2

    word_global_idx = 0
    for line in lines:
        word_sizes = []
        for w in line:
            bbox = draw.textbbox((0, 0), w + " ", font=font)
            word_sizes.append((bbox[2] - bbox[0], bbox[3] - bbox[1]))

        total_line_w = sum(ws[0] for ws in word_sizes)
        x = (W - total_line_w) // 2
        y = start_y

        for i, w in enumerate(line):
            is_current = (word_global_idx == current_word_idx)
            color = hex_to_rgb(highlight_color) if is_current else hex_to_rgb(font_color)
            stroke_clr = hex_to_rgb(stroke_color)

            # Draw stroke/outline
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
    W: int,
    H: int,
    style: dict,
    font_path: str,
) -> list:
    """Build per-word ImageClips for the animated caption overlay."""
    clips = []
    font_size = style.get("font_size", DEFAULT_FONT_SIZE)
    font_color = style.get("font_color", DEFAULT_FONT_COLOR)
    highlight_color = style.get("highlight_color", DEFAULT_HIGHLIGHT_COLOR)
    stroke_color = style.get("stroke_color", DEFAULT_STROKE_COLOR)
    stroke_width = style.get("stroke_width", DEFAULT_STROKE_WIDTH)
    max_words = style.get("max_words_per_line", DEFAULT_MAX_WORDS)

    for chunk in caption_chunks:
        for word_idx, word in enumerate(chunk["words"]):
            word_start = word["start"]
            word_end = word["end"]
            duration = word_end - word_start

            if duration <= 0 or word_start >= total_duration:
                continue

            frame = _render_caption_frame(
                chunk=chunk,
                current_word_idx=word_idx,
                W=W,
                H=H,
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
    clip_paths: list[str],
    audio_path: str,
    caption_chunks: list[dict],
    output_path: str,
    channel_cfg: dict,
    global_cfg: dict,
    music_path: str | None = None,
) -> str:
    """
    Assemble the final reel video from multiple background clips.

    Args:
        clip_paths     : List of 3-4 background .mp4 file paths.
        audio_path     : TTS voiceover .mp3.
        caption_chunks : Word-timed caption chunks from caption_generator.
        output_path    : Output .mp4 path.
        channel_cfg    : Channel config dict.
        global_cfg     : Global config dict.
        music_path     : Optional background music .mp3 (mixed at 20% volume).

    Returns:
        Path to the rendered video.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    W = global_cfg.get("video_width", DEFAULT_W)
    H = global_cfg.get("video_height", DEFAULT_H)
    font_path = global_cfg.get("font_path", DEFAULT_FONT_PATH)
    caption_style = channel_cfg.get("caption_style", {})

    # ── Load TTS audio ─────────────────────────────────────────────────────────
    logger.info("Loading TTS audio...")
    tts_audio = AudioFileClip(audio_path)
    total_duration = tts_audio.duration
    logger.info(f"Total duration: {total_duration:.2f}s")

    # ── Build background from multiple clips ───────────────────────────────────
    logger.info(f"Building background from {len(clip_paths)} clips...")
    bg = _build_background(clip_paths, total_duration, W, H)

    # ── Dark overlay ───────────────────────────────────────────────────────────
    overlay = (
        ColorClip(size=(W, H), color=(0, 0, 0))
        .set_opacity(0.40)
        .set_duration(total_duration)
    )

    # ── Caption clips ──────────────────────────────────────────────────────────
    logger.info("Rendering caption clips...")
    caption_clips = _make_caption_clips(
        caption_chunks=caption_chunks,
        total_duration=total_duration,
        W=W,
        H=H,
        style=caption_style,
        font_path=font_path,
    )

    # ── Composite video ────────────────────────────────────────────────────────
    logger.info("Compositing video layers...")
    all_layers = [bg, overlay] + caption_clips
    final_video = CompositeVideoClip(all_layers, size=(W, H))
    final_video = final_video.set_duration(total_duration)

    # ── Mix audio (TTS + background music at 20%) ──────────────────────────────
    if music_path and os.path.exists(music_path):
        logger.info(f"Mixing background music at {int(MUSIC_VOLUME*100)}% volume...")
        try:
            music = AudioFileClip(music_path).volumex(MUSIC_VOLUME)

            # Loop music if shorter than video
            if music.duration < total_duration:
                loops = int(total_duration / music.duration) + 1
                music = concatenate_audioclips([music] * loops)

            music = music.subclip(0, total_duration)

            # Fade music out in last 2 seconds
            music = music.audio_fadeout(2.0)

            # Composite TTS + music
            final_audio = CompositeAudioClip([tts_audio, music])
            final_video = final_video.set_audio(final_audio)
            logger.info("Background music mixed successfully.")
        except Exception as e:
            logger.warning(f"Music mixing failed ({e}) — using TTS only.")
            final_video = final_video.set_audio(tts_audio)
    else:
        if music_path:
            logger.warning(f"Music file not found: {music_path} — using TTS only.")
        final_video = final_video.set_audio(tts_audio)

    # ── Export ─────────────────────────────────────────────────────────────────
    logger.info(f"Exporting -> {output_path}")
    os.makedirs("temp", exist_ok=True)
    final_video.write_videofile(
        output_path,
        fps=30,
        codec="libx264",
        audio_codec="aac",
        temp_audiofile="temp/temp_audio.m4a",
        remove_temp=True,
        logger=None,
        threads=4,
    )

    # Cleanup
    try:
        tts_audio.close()
        bg.close()
        final_video.close()
    except Exception:
        pass

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    logger.info(f"Video exported ({size_mb:.1f} MB): {output_path}")
    return output_path
