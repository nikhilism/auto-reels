"""
clip_effects.py
───────────────
Applies cinematic effects to video clips based on analysis results:

  - Smart 9:16 crop (centers on motion area)
  - Color grading presets (racing, cold, cinematic, vibrant, warm, gaming)
  - Speed ramp (slow-mo at peak moment, slightly faster elsewhere)
  - Zoom pulse (subtle punch-in at peak moment)
  - Vignette overlay (darkened edges for cinematic look)

All effects are non-destructive and run through MoviePy's frame pipeline.
"""

import logging
import os
import hashlib
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter
from moviepy.editor import (
    VideoFileClip,
    concatenate_videoclips,
    ImageClip,
    CompositeVideoClip,
)

from src.clip_analyzer import AnalysisResult

logger = logging.getLogger(__name__)

TARGET_W = 1080
TARGET_H = 1920

# ── Color grade recipes ────────────────────────────────────────────────────────
# Each grade: (saturation_mult, contrast_mult, brightness_mult, warmth_shift)
# warmth_shift: positive = warmer (boost red, reduce blue), negative = cooler
GRADE_PRESETS = {
    "racing": {
        "saturation": 1.55,
        "contrast":   1.25,
        "brightness": 1.05,
        "warmth":     18,    # warm orange boost
        "sharpness":  1.2,
    },
    "cold": {
        "saturation": 1.3,
        "contrast":   1.4,
        "brightness": 0.95,
        "warmth":     -20,   # cool blue tone
        "sharpness":  1.3,
    },
    "cinematic": {
        "saturation": 1.2,
        "contrast":   1.15,
        "brightness": 0.98,
        "warmth":     8,     # slight teal-orange
        "sharpness":  1.1,
    },
    "vibrant": {
        "saturation": 1.6,
        "contrast":   1.2,
        "brightness": 1.05,
        "warmth":     5,
        "sharpness":  1.2,
    },
    "warm": {
        "saturation": 1.15,
        "contrast":   1.1,
        "brightness": 1.08,
        "warmth":     12,
        "sharpness":  1.0,
    },
    "gaming": {
        "saturation": 1.4,
        "contrast":   1.2,
        "brightness": 1.02,
        "warmth":     6,
        "sharpness":  1.15,
    },
}


def process_clip(
    clip_path: str,
    analysis: AnalysisResult,
    output_dir: str,
    num_segments: int = 1,
) -> list[str]:
    """
    Process a raw clip into one or more reel-ready 9:16 segments.

    Args:
        clip_path    : Path to source video file.
        analysis     : AnalysisResult from clip_analyzer.
        output_dir   : Where to save output segments.
        num_segments : How many segments to extract from this clip.

    Returns:
        List of output file paths.
    """
    os.makedirs(output_dir, exist_ok=True)

    logger.info(f"Processing: {os.path.basename(clip_path)}")
    logger.info(
        f"Content: {analysis.content_type} | "
        f"Score: {analysis.excitement_score}/10 | "
        f"Grade: {analysis.color_grade}"
    )

    clip = VideoFileClip(clip_path, audio=True)
    duration = clip.duration
    outputs = []

    # Determine segment windows
    segments = _plan_segments(analysis, duration, num_segments)
    logger.info(f"Extracting {len(segments)} segment(s): {[(f'{s:.1f}', f'{e:.1f}') for s,e in segments]}")

    # Generate vignette once (reuse across segments)
    vignette = _make_vignette(TARGET_W, TARGET_H)

    for idx, (seg_start, seg_end) in enumerate(segments):
        logger.info(f"  Segment {idx+1}: {seg_start:.1f}s → {seg_end:.1f}s")

        # Extract segment
        segment = clip.subclip(seg_start, seg_end)

        # Apply speed ramp if requested
        if "speed_ramp" in analysis.effects:
            local_peak = analysis.peak_moment - seg_start
            segment = _apply_speed_ramp(segment, local_peak)

        # Crop to 9:16 (smart crop using motion-weighted center)
        segment = _smart_crop(segment, TARGET_W, TARGET_H)

        # Apply zoom pulse at peak moment
        if "zoom_pulse" in analysis.effects:
            local_peak = max(0, analysis.peak_moment - seg_start)
            segment = _apply_zoom_pulse(segment, local_peak, segment.duration)

        # Color grade (per-frame PIL enhancement)
        segment = _apply_color_grade(segment, analysis.color_grade)

        # Vignette overlay
        if "vignette" in analysis.effects:
            vignette_clip = ImageClip(vignette, ismask=False).set_duration(segment.duration)
            segment = CompositeVideoClip([segment, vignette_clip])

        # Build output filename
        base = os.path.splitext(os.path.basename(clip_path))[0]
        safe_base = "".join(c if c.isalnum() or c in "_-" else "_" for c in base)[:40]
        out_name = f"{safe_base}_seg{idx+1:02d}_{analysis.content_type}.mp4"
        out_path = os.path.join(output_dir, out_name)

        logger.info(f"  Exporting: {out_name}")
        segment.write_videofile(
            out_path,
            fps=30,
            codec="libx264",
            audio_codec="aac",
            temp_audiofile=f"temp/cs_temp_{idx}.m4a",
            remove_temp=True,
            logger=None,
            threads=4,
        )

        try:
            segment.close()
        except Exception:
            pass

        outputs.append(out_path)

    clip.close()
    return outputs


def _plan_segments(
    analysis: AnalysisResult,
    duration: float,
    num_segments: int,
    seg_length: float = 13.0,
) -> list[tuple[float, float]]:
    """
    Plan segment windows to extract from the clip.
    Priority: peak moment first, then spread across the clip.
    """
    segments = []
    half = seg_length / 2

    if num_segments == 1:
        # Just the peak highlight
        peak = max(half, min(duration - half, analysis.peak_moment))
        return [(max(0, peak - half), min(duration, peak + half))]

    # Multiple segments: peak first, then spread the rest evenly
    peak = max(half, min(duration - half, analysis.peak_moment))
    segments.append((max(0, peak - half), min(duration, peak + half)))

    # Distribute remaining segments evenly
    remaining = num_segments - 1
    step = duration / (remaining + 1)
    for i in range(1, remaining + 1):
        t = step * i
        if abs(t - peak) < seg_length:  # too close to peak, shift
            t = t + seg_length if t < peak else t - seg_length
        t = max(half, min(duration - half, t))
        seg = (max(0, t - half), min(duration, t + half))
        # Avoid duplicate / overlapping windows
        if not any(abs(seg[0] - ex[0]) < seg_length / 2 for ex in segments):
            segments.append(seg)

    return segments[:num_segments]


def _smart_crop(clip: VideoFileClip, W: int, H: int) -> VideoFileClip:
    """
    Crop clip to W x H.
    Tries to keep the center-of-action in frame using a quick motion scan.
    Falls back to pure center-crop if analysis is too slow.
    """
    src_w, src_h = clip.w, clip.h
    target_aspect = W / H  # 9:16 = 0.5625
    src_aspect = src_w / src_h

    if src_aspect > target_aspect:
        # Wider than 9:16 — need to crop horizontally
        # Quick motion scan: sample a few frames and find active horizontal zone
        new_h = src_h
        new_w = int(src_h * target_aspect)
        cx = _find_horizontal_center(clip, src_w, src_h, new_w)
        x1 = max(0, min(cx - new_w // 2, src_w - new_w))
        clip = clip.crop(x1=x1, y1=0, x2=x1 + new_w, y2=new_h)
    else:
        # Taller than 9:16 — crop vertically (center)
        new_w = src_w
        new_h = int(src_w / target_aspect)
        y1 = max(0, (src_h - new_h) // 2)
        clip = clip.crop(x1=0, y1=y1, x2=new_w, y2=y1 + new_h)

    # Final resize to exact target
    return clip.resize((W, H))


def _find_horizontal_center(clip, src_w: int, src_h: int, crop_w: int) -> int:
    """
    Find the horizontal center with most motion using 5 sampled frames.
    Returns the ideal x-center for the crop.
    """
    try:
        sample_times = np.linspace(1.0, max(1.5, clip.duration - 0.5), 5)
        motion_cols = np.zeros(src_w)
        prev_frame = None

        for t in sample_times:
            frame = clip.get_frame(float(t))
            if prev_frame is not None:
                diff = np.abs(
                    frame.astype(float) - prev_frame.astype(float)
                ).mean(axis=(0, 2))  # mean over rows and channels -> per-column score
                diff_resized = np.interp(
                    np.linspace(0, len(diff) - 1, src_w),
                    np.arange(len(diff)),
                    diff,
                )
                motion_cols += diff_resized
            prev_frame = frame

        # Find column with peak cumulative motion
        peak_col = int(np.argmax(motion_cols))
        # Clamp to valid crop range
        return max(crop_w // 2, min(src_w - crop_w // 2, peak_col))
    except Exception:
        return src_w // 2  # fallback to center


def _apply_color_grade(clip: VideoFileClip, grade_name: str) -> VideoFileClip:
    """Apply a color grade preset to every frame using PIL."""
    preset = GRADE_PRESETS.get(grade_name, GRADE_PRESETS["gaming"])

    sat   = preset["saturation"]
    con   = preset["contrast"]
    bri   = preset["brightness"]
    warm  = preset["warmth"]
    sharp = preset["sharpness"]

    def grade_frame(frame: np.ndarray) -> np.ndarray:
        img = Image.fromarray(frame.astype(np.uint8))

        # Saturation
        img = ImageEnhance.Color(img).enhance(sat)
        # Contrast
        img = ImageEnhance.Contrast(img).enhance(con)
        # Brightness
        img = ImageEnhance.Brightness(img).enhance(bri)
        # Sharpness
        img = ImageEnhance.Sharpness(img).enhance(sharp)

        # Warmth (shift red/blue channels)
        if warm != 0:
            r, g, b = img.split()
            shift = abs(warm)
            if warm > 0:
                # Warmer: boost red, reduce blue
                r = r.point(lambda x: min(255, x + shift))
                b = b.point(lambda x: max(0, x - shift // 2))
            else:
                # Cooler: boost blue, reduce red
                b = b.point(lambda x: min(255, x + shift))
                r = r.point(lambda x: max(0, x - shift // 2))
            img = Image.merge("RGB", (r, g, b))

        return np.array(img)

    return clip.fl_image(grade_frame)


def _apply_speed_ramp(clip: VideoFileClip, peak_time: float) -> VideoFileClip:
    """
    Speed ramp: slow down around the peak moment (0.7x),
    slightly speed up other sections (1.2x).
    Preserves the feel of the action while keeping duration manageable.
    """
    duration = clip.duration
    ramp_window = 3.0   # seconds around peak to slow down
    slow_speed = 0.7
    fast_speed = 1.2

    t_start = max(0.0, peak_time - ramp_window / 2)
    t_end = min(duration, peak_time + ramp_window / 2)

    parts = []
    if t_start > 0.1:
        before = clip.subclip(0, t_start).speedx(fast_speed)
        parts.append(before)

    peak_seg = clip.subclip(t_start, t_end).speedx(slow_speed)
    parts.append(peak_seg)

    if t_end < duration - 0.1:
        after = clip.subclip(t_end, duration).speedx(fast_speed)
        parts.append(after)

    if not parts:
        return clip

    return concatenate_videoclips(parts)


def _apply_zoom_pulse(
    clip: VideoFileClip,
    peak_time: float,
    duration: float,
    zoom_max: float = 1.12,
) -> VideoFileClip:
    """
    Subtle zoom punch at the peak moment.
    Smoothly zooms from 1.0x → 1.12x → 1.0x around the peak.
    """
    W, H = clip.w, clip.h

    def zoom_at_time(t):
        # Gaussian-shaped zoom centered on peak_time
        sigma = 1.5
        z = 1.0 + (zoom_max - 1.0) * np.exp(-((t - peak_time) ** 2) / (2 * sigma ** 2))
        return float(z)

    def make_frame(t):
        frame = clip.get_frame(t)
        z = zoom_at_time(t)
        if abs(z - 1.0) < 0.005:
            return frame
        img = Image.fromarray(frame.astype(np.uint8))
        new_w = int(W / z)
        new_h = int(H / z)
        x1 = (W - new_w) // 2
        y1 = (H - new_h) // 2
        cropped = img.crop((x1, y1, x1 + new_w, y1 + new_h))
        return np.array(cropped.resize((W, H), Image.LANCZOS))

    return clip.fl(lambda gf, t: make_frame(t), apply_to=["mask"])


def _make_vignette(W: int, H: int, strength: float = 0.55) -> np.ndarray:
    """
    Generate a vignette overlay (dark edges, transparent center).
    Returns RGBA numpy array.
    """
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pixels = np.array(img, dtype=float)

    cx, cy = W / 2, H / 2
    for y in range(H):
        for x in range(W):
            dx = (x - cx) / cx
            dy = (y - cy) / cy
            dist = min(1.0, (dx ** 2 + dy ** 2) ** 0.5)
            alpha = int(dist ** 2 * strength * 200)
            pixels[y, x] = [0, 0, 0, alpha]

    return pixels.astype(np.uint8)
