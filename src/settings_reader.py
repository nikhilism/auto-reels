"""
settings_reader.py
──────────────────
Reads the user-friendly settings.txt file and returns parsed values.
Handles comments (#), blank lines, and case-insensitive keys.
"""

import logging
import os

logger = logging.getLogger(__name__)

SETTINGS_FILE = "settings.txt"

# Maps highlight color names to hex codes
COLOR_MAP = {
    "gold":   "#FFD700",
    "red":    "#FF4500",
    "cyan":   "#00CFFF",
    "green":  "#00FF88",
    "white":  "#FFFFFF",
    "purple": "#BF5FFF",
    "yellow": "#FFFF00",
    "orange": "#FF8C00",
    "pink":   "#FF69B4",
    "blue":   "#4169E1",
}


def _parse_settings(filepath: str) -> dict:
    """Parse key=value settings file, ignoring comments and blank lines."""
    settings = {}
    if not os.path.exists(filepath):
        return settings

    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            # Skip comments and blank lines
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip().lower()
            value = value.strip()
            settings[key] = value

    return settings


def load_settings() -> dict:
    """
    Load and return parsed user settings from settings.txt.

    Returns a dict with clean, ready-to-use values:
      {
        "topics": {
            "gaming": "GTA 5 secrets" or None,
            "drawing": None,
            "informative": "why do we dream",
        },
        "enabled": {
            "gaming": True,
            "drawing": True,
            "informative": False,
        },
        "highlight_colors": {
            "gaming": "#FF4500",
            ...
        },
        "auto_upload": {
            "gaming": False,
            ...
        },
      }
    """
    raw = _parse_settings(SETTINGS_FILE)

    channels = ["gaming", "drawing", "informative"]

    # ── Topic overrides ───────────────────────────────────────────────────────
    topics = {}
    for ch in channels:
        val = raw.get(f"{ch}_topic", "").strip()
        topics[ch] = val if val else None

    # ── Channel enabled flags ─────────────────────────────────────────────────
    enabled = {}
    for ch in channels:
        val = raw.get(f"run_{ch}", "yes").strip().lower()
        enabled[ch] = val in ("yes", "true", "1", "on")

    # ── Highlight colors ──────────────────────────────────────────────────────
    colors = {}
    for ch in channels:
        val = raw.get(f"{ch}_highlight", "").strip().lower()
        if val.startswith("#"):
            colors[ch] = val.upper()
        elif val in COLOR_MAP:
            colors[ch] = COLOR_MAP[val]
        else:
            colors[ch] = None  # Use config.yaml default

    # ── Auto upload ───────────────────────────────────────────────────────────
    auto_upload = {}
    for ch in channels:
        val = raw.get(f"{ch}_auto_upload", "no").strip().lower()
        auto_upload[ch] = val in ("yes", "true", "1", "on")

    result = {
        "topics": topics,
        "enabled": enabled,
        "highlight_colors": colors,
        "auto_upload": auto_upload,
    }

    # Log what was loaded
    for ch in channels:
        topic_str = f"'{topics[ch]}'" if topics[ch] else "random"
        status = "ON" if enabled[ch] else "OFF"
        logger.info(f"Settings [{ch}]: {status}, topic={topic_str}")

    return result
