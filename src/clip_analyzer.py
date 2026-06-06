"""
clip_analyzer.py
────────────────
Analyzes video clips using Gemini Vision + motion detection to understand:
  - What type of content is in the clip (racing, shooter, open world, etc.)
  - The most exciting/high-action moment (for highlight extraction)
  - Recommended color grade and effects for that content type
  - An overall excitement score

Two analysis methods:
  1. Gemini Vision (primary) — actual AI understanding of game content
  2. Motion detection (fallback/supplemental) — finds peak action frames
"""

import json
import logging
import os
import re

import numpy as np
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    """Structured result from clip analysis."""
    content_type: str = "gaming"        # racing, shooter, open_world, sports, drawing, other
    excitement_score: float = 7.0       # 1–10
    peak_moment: float = 5.0            # seconds into clip with most action
    highlight_start: float = 0.0        # suggested highlight segment start
    highlight_end: float = 13.0         # suggested highlight segment end
    color_grade: str = "gaming"         # gaming, racing, cinematic, warm, cold
    effects: list = field(default_factory=lambda: ["color_boost"])
    description: str = ""               # Gemini's summary of what's happening
    clip_duration: float = 0.0


# ── Per content type: what effects to apply ───────────────────────────────────
CONTENT_EFFECTS = {
    "racing": {
        "color_grade": "racing",   # warm orange/yellow, high saturation
        "effects": ["color_boost", "speed_ramp", "vignette"],
    },
    "shooter": {
        "color_grade": "cold",     # cold blue tones, high contrast
        "effects": ["color_boost", "zoom_pulse", "vignette"],
    },
    "open_world": {
        "color_grade": "cinematic",  # teal-orange Hollywood look
        "effects": ["color_boost", "vignette"],
    },
    "sports": {
        "color_grade": "vibrant",  # vivid, high saturation
        "effects": ["color_boost", "speed_ramp"],
    },
    "drawing": {
        "color_grade": "warm",     # soft warm tones
        "effects": ["color_boost"],
    },
    "gameplay": {
        "color_grade": "gaming",   # boosted gaming look
        "effects": ["color_boost", "vignette"],
    },
    "other": {
        "color_grade": "gaming",
        "effects": ["color_boost"],
    },
}


def analyze_clip(clip_path: str, channel_id: str = "gaming") -> AnalysisResult:
    """
    Analyze a video clip using Gemini Vision + motion detection.

    Args:
        clip_path  : Path to the video file.
        channel_id : Channel type (gaming/drawing/informative).

    Returns:
        AnalysisResult with content understanding and editing recommendations.
    """
    from moviepy.editor import VideoFileClip

    logger.info(f"Loading clip for analysis: {os.path.basename(clip_path)}")
    clip = VideoFileClip(clip_path, audio=False)
    duration = clip.duration
    logger.info(f"Duration: {duration:.1f}s")

    # ── Motion detection (fast, no API) ───────────────────────────────────────
    logger.info("Running motion detection...")
    peak_time, motion_scores = _detect_motion_peak(clip)
    logger.info(f"Motion peak at: {peak_time:.1f}s")

    # ── Gemini Vision analysis (smart content understanding) ──────────────────
    gemini_result = None
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        try:
            logger.info("Analyzing with Gemini Vision...")
            gemini_result = _analyze_with_gemini(clip, duration, channel_id)
            if gemini_result:
                logger.info(f"Gemini: {gemini_result.get('content_type')} (score {gemini_result.get('excitement_score')})")
        except Exception as e:
            logger.warning(f"Gemini Vision failed: {e}. Using motion detection only.")

    clip.close()

    # ── Build final result ────────────────────────────────────────────────────
    return _build_result(
        gemini_result=gemini_result,
        motion_peak=peak_time,
        duration=duration,
        channel_id=channel_id,
    )


def _detect_motion_peak(clip) -> tuple[float, list]:
    """
    Find the timestamp with peak motion in the clip.
    Samples frames every 0.5 seconds and computes frame-to-frame difference.

    Returns:
        (peak_timestamp_seconds, list_of_(time, score)_tuples)
    """
    duration = clip.duration
    sample_interval = 0.5
    timestamps = np.arange(0, duration - sample_interval, sample_interval)

    scores = []
    prev_frame = None

    for t in timestamps:
        try:
            frame = clip.get_frame(t)
            # Downsample for speed
            small = frame[::4, ::4]
            if prev_frame is not None:
                diff = np.mean(np.abs(small.astype(float) - prev_frame.astype(float)))
                scores.append((float(t), float(diff)))
            prev_frame = small
        except Exception:
            pass

    if not scores:
        return duration / 2, []

    # Smooth the motion curve
    if len(scores) > 5:
        raw_scores = [s[1] for s in scores]
        smoothed = _smooth(raw_scores, window=5)
        scores = [(scores[i][0], smoothed[i]) for i in range(len(scores))]

    peak = max(scores, key=lambda x: x[1])
    return peak[0], scores


def _smooth(data: list, window: int = 5) -> list:
    """Moving average smoothing."""
    result = []
    half = window // 2
    for i in range(len(data)):
        start = max(0, i - half)
        end = min(len(data), i + half + 1)
        result.append(sum(data[start:end]) / (end - start))
    return result


def _analyze_with_gemini(clip, duration: float, channel_id: str) -> dict | None:
    """
    Extract frames and send to Gemini Vision for content analysis.
    Returns a dict with: content_type, excitement_score, best_segment_start,
    color_grade, effects, description.
    """
    import google.generativeai as genai
    from PIL import Image

    api_key = os.getenv("GEMINI_API_KEY")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")

    # Extract 5 evenly-spaced frames
    sample_times = np.linspace(0.5, duration - 0.5, 5)
    frames = []
    for t in sample_times:
        try:
            frame_array = clip.get_frame(float(t))
            # Resize to reduce API payload
            pil_img = Image.fromarray(frame_array).resize((480, 270), Image.LANCZOS)
            frames.append(pil_img)
        except Exception as e:
            logger.debug(f"Frame extraction failed at {t:.1f}s: {e}")

    if not frames:
        return None

    channel_context = {
        "gaming": "This is from a gaming channel focused on gameplay footage (GTA, Forza Horizon, etc.)",
        "drawing": "This is from an art/drawing channel showing artwork creation.",
        "informative": "This is from an informative/documentary-style channel.",
    }.get(channel_id, "This is a content creation video.")

    prompt = f"""You are a professional video editor analyzing footage for short-form social media content.

{channel_context}

I'm showing you {len(frames)} evenly-spaced frames from a video clip.
Analyze them and return ONLY valid JSON (no markdown, no explanation):

{{
  "content_type": "one of: racing, shooter, open_world, sports, drawing, gameplay, other",
  "excitement_score": <float 1-10, how exciting/engaging is this for short-form content>,
  "best_segment_description": "<what is the most exciting thing happening>",
  "color_grade": "one of: racing (warm/orange), cold (blue/dark), cinematic (teal-orange), vibrant (saturated), warm (soft), gaming (boosted)",
  "effects": ["list from: color_boost, speed_ramp, zoom_pulse, vignette, motion_blur"],
  "description": "<1-2 sentence summary of what's in this clip>",
  "why_exciting": "<what makes this good for short-form content>"
}}"""

    content = [prompt] + frames

    response = model.generate_content(content)
    raw = response.text.strip()

    # Strip markdown fences
    raw = re.sub(r"^```[a-z]*\n?", "", raw).strip()
    raw = re.sub(r"\n?```$", "", raw).strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning(f"Gemini returned invalid JSON: {e}")
        return None


def _build_result(
    gemini_result: dict | None,
    motion_peak: float,
    duration: float,
    channel_id: str,
) -> AnalysisResult:
    """Merge Gemini + motion data into a final AnalysisResult."""

    # Defaults based on channel
    default_content_type = {
        "gaming": "gameplay",
        "drawing": "drawing",
        "informative": "other",
    }.get(channel_id, "other")

    if gemini_result:
        raw_type = gemini_result.get("content_type", default_content_type).lower()
        content_type = raw_type if raw_type in CONTENT_EFFECTS else default_content_type
        excitement = float(gemini_result.get("excitement_score", 7.0))
        description = gemini_result.get("description", "")
        color_grade = gemini_result.get("color_grade", CONTENT_EFFECTS[content_type]["color_grade"])
        effects = gemini_result.get("effects", CONTENT_EFFECTS[content_type]["effects"])
    else:
        content_type = default_content_type
        excitement = 7.0
        description = f"Auto-analyzed {channel_id} clip"
        color_grade = CONTENT_EFFECTS[content_type]["color_grade"]
        effects = CONTENT_EFFECTS[content_type]["effects"]

    # Determine best highlight window (12-15 seconds around peak)
    segment_len = 13.0
    half = segment_len / 2
    peak = max(half, min(duration - half, motion_peak))
    h_start = max(0.0, peak - half)
    h_end = min(duration, h_start + segment_len)

    return AnalysisResult(
        content_type=content_type,
        excitement_score=excitement,
        peak_moment=motion_peak,
        highlight_start=h_start,
        highlight_end=h_end,
        color_grade=color_grade,
        effects=effects,
        description=description,
        clip_duration=duration,
    )
