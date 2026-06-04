"""
script_generator.py
───────────────────
Uses Google Gemini API to generate a short-form video script
and associated metadata (title, description, hashtags, Pexels keywords)
for a given channel configuration.

API key is loaded from .env — never hardcoded.
"""

import os
import json
import random
import logging
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()
logger = logging.getLogger(__name__)

# ── Per-channel cinematic fallback queries for Pexels ─────────────────────────
# Used when Gemini's queries don't find good results.
# These are guaranteed to return great vertical stock footage.
CHANNEL_FALLBACK_QUERIES = {
    "gaming": [
        "neon city night streets",
        "sports car driving fast highway",
        "city lights aerial view night",
        "racing car speed blur",
        "luxury car showroom",
        "urban street night rain",
        "cyberpunk city neon lights",
        "motorcycle highway speed",
    ],
    "drawing": [
        "artist painting canvas studio",
        "colorful paint splashing",
        "paintbrush watercolor paper",
        "pencil sketching hand close up",
        "art supplies colorful",
        "creative workspace desk",
        "hands drawing sketchbook",
        "paint palette colors",
    ],
    "informative": [
        "space galaxy stars universe",
        "science laboratory research",
        "nature aerial landscape",
        "ocean underwater blue",
        "ancient ruins architecture",
        "futuristic technology digital",
        "earth from above clouds",
        "documentary nature wildlife",
    ],
}


def _get_client() -> genai.GenerativeModel:
    """Initialize Gemini client from env var."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "GEMINI_API_KEY is not set. "
            "Copy .env.example to .env and add your key."
        )
    genai.configure(api_key=api_key)
    return genai.GenerativeModel("gemini-2.5-flash")


def generate_script(channel_cfg: dict, topic_override: str = None) -> dict:
    """
    Generate a complete reel script and metadata for a channel.

    Args:
        channel_cfg    : A single channel's config dict from config.yaml.
        topic_override : If provided, use this topic instead of random selection.

    Returns:
        dict with keys:
          - script        : str  — the spoken voiceover text
          - title         : str  — YouTube/Instagram title
          - description   : str  — post description
          - hashtags      : list — relevant hashtags
          - pexels_queries: list — cinematic search terms for background video
    """
    model = _get_client()

    niche = channel_cfg["niche"]
    tone = channel_cfg["tone"]
    channel_id = channel_cfg.get("channel_id", "informative")

    # Use override topic or pick randomly from config list
    if topic_override and topic_override.strip():
        topic = topic_override.strip()
        logger.info(f"Using user-specified topic: '{topic}'")
    else:
        topic = random.choice(channel_cfg["topics"])
        logger.info(f"Using random topic: '{topic}'")

    logger.info(f"Generating script for: '{topic}' (niche: {niche})")

    # Get channel-specific fallback queries to guide Gemini's style
    fallbacks = CHANNEL_FALLBACK_QUERIES.get(channel_id, CHANNEL_FALLBACK_QUERIES["informative"])
    example_queries = ", ".join(f'"{q}"' for q in fallbacks[:4])

    prompt = f"""
You are a viral short-form video scriptwriter. Write a script for a YouTube Short / Instagram Reel.

Channel niche: {niche}
Topic: {topic}
Tone: {tone}
Target duration: ~55 seconds (approximately 130-150 words spoken at a normal energetic pace)

SCRIPT RULES:
- ONLY the spoken words — no stage directions, no [music], no (pause), no brackets of any kind
- First sentence must be a POWERFUL hook that stops the scroll immediately
- Short punchy sentences — this is spoken aloud, not read
- End with a strong call to action (follow, like, comment)

PEXELS QUERY RULES (very important):
- These are used to find STOCK VIDEO FOOTAGE on Pexels.com
- Pexels has NO game footage, NO branded content, NO TV/movie clips
- Use VISUAL and CINEMATIC descriptions only — describe what the camera sees
- Think: nature, cities, cars, space, people, abstract, architecture, technology
- Example good queries: {example_queries}
- BAD examples (never use): "GTA 5 gameplay", "Forza Horizon race", "SpongeBob scene"

OUTPUT FORMAT: Return ONLY valid JSON (no markdown fences, no extra text):
{{
  "script": "Full spoken script here...",
  "title": "Catchy YouTube Shorts title (max 60 chars, use CAPS for impact)",
  "description": "2-3 sentence description for the post",
  "hashtags": ["hashtag1", "hashtag2", "hashtag3", "hashtag4", "hashtag5", "hashtag6"],
  "pexels_queries": ["cinematic query 1", "cinematic query 2", "cinematic query 3", "cinematic query 4"]
}}
"""

    response = model.generate_content(prompt)
    raw = response.text.strip()

    # Strip markdown code fences if Gemini wraps in them
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    if raw.endswith("```"):
        raw = raw[: raw.rfind("```")].strip()

    try:
        result = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Gemini JSON response: {e}\nRaw: {raw}")
        raise ValueError(f"Gemini returned invalid JSON: {e}") from e

    # Validate required keys
    required = ["script", "title", "description", "hashtags", "pexels_queries"]
    for key in required:
        if key not in result:
            raise ValueError(f"Gemini response missing key: '{key}'")

    # Append channel-specific fallback queries so asset_fetcher always has backups
    result["pexels_queries"] = result["pexels_queries"] + fallbacks[:3]

    logger.info(f"Script generated. Title: {result['title']}")
    return result
