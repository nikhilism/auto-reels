"""
music_fetcher.py
────────────────
Downloads royalty-free background music from the Jamendo API (free).

Jamendo is a legal, royalty-free music platform with a free API.
Get a free client ID at: https://developer.jamendo.com/v3.0

API key (client_id) is loaded from .env as JAMENDO_CLIENT_ID.
Music is cached in assets/music/ to avoid re-downloading.
"""

import hashlib
import logging
import os
import random
import requests
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

JAMENDO_API = "https://api.jamendo.com/v3.0/tracks/"
MUSIC_CACHE_DIR = "assets/music/cache"

# Royalty-free music search tags per channel mood
CHANNEL_MUSIC_TAGS = {
    "gaming": ["electronic", "energetic", "action", "upbeat"],
    "drawing": ["ambient", "piano", "calm", "lofi"],
    "informative": ["cinematic", "atmospheric", "documentary", "inspiring"],
}

# Fallback: known stable royalty-free music URLs (no API key needed)
# These are from the Free Music Archive / Pixabay CDN and are CC0 licensed
FALLBACK_MUSIC = {
    "gaming": [
        "https://cdn.pixabay.com/download/audio/2022/08/02/audio_884fe92c21.mp3",
        "https://cdn.pixabay.com/download/audio/2022/01/18/audio_d1718ab41b.mp3",
    ],
    "drawing": [
        "https://cdn.pixabay.com/download/audio/2022/05/27/audio_1808fbf07a.mp3",
        "https://cdn.pixabay.com/download/audio/2021/11/25/audio_5b31e04f70.mp3",
    ],
    "informative": [
        "https://cdn.pixabay.com/download/audio/2022/03/10/audio_c8c8a73467.mp3",
        "https://cdn.pixabay.com/download/audio/2021/08/04/audio_c518c8d0d1.mp3",
    ],
}


def fetch_background_music(channel_id: str, output_path: str) -> str | None:
    """
    Download a royalty-free background music track for the given channel.

    Tries Jamendo API first (if JAMENDO_CLIENT_ID is set),
    then falls back to curated CDN tracks.

    Args:
        channel_id  : e.g. "gaming", "drawing", "informative"
        output_path : Where to save the .mp3 file.

    Returns:
        Path to downloaded music file, or None if all sources fail.
    """
    os.makedirs(MUSIC_CACHE_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    client_id = os.getenv("JAMENDO_CLIENT_ID", "").strip()

    if client_id:
        result = _fetch_from_jamendo(client_id, channel_id, output_path)
        if result:
            return result
        logger.warning("Jamendo fetch failed — falling back to CDN tracks.")

    return _fetch_fallback(channel_id, output_path)


def _fetch_from_jamendo(client_id: str, channel_id: str, output_path: str) -> str | None:
    """Search Jamendo and download a matching track."""
    tags = CHANNEL_MUSIC_TAGS.get(channel_id, ["ambient"])

    for tag in tags:
        cache_key = hashlib.md5(f"jamendo_{channel_id}_{tag}".encode()).hexdigest()
        cached = os.path.join(MUSIC_CACHE_DIR, f"{cache_key}.mp3")
        if os.path.exists(cached):
            logger.info(f"Using cached Jamendo track: {cached}")
            _copy_file(cached, output_path)
            return output_path

        try:
            params = {
                "client_id": client_id,
                "format": "json",
                "tags": tag,
                "audiodownload_allowed": "true",
                "limit": 10,
                "include": "musicinfo",
                "groupby": "artist_id",
            }
            resp = requests.get(JAMENDO_API, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])

            # Filter to tracks with a downloadable audio URL
            downloadable = [
                t for t in results
                if t.get("audiodownload") and t.get("audiodownload_allowed")
            ]
            if not downloadable:
                continue

            track = random.choice(downloadable[:5])
            audio_url = track["audiodownload"]
            logger.info(
                f"Downloading Jamendo track: '{track.get('name')}' "
                f"by {track.get('artist_name')} (tag: {tag})"
            )
            _download_file(audio_url, cached)
            _copy_file(cached, output_path)
            return output_path

        except Exception as e:
            logger.warning(f"Jamendo search failed for tag '{tag}': {e}")
            continue

    return None


def _fetch_fallback(channel_id: str, output_path: str) -> str | None:
    """Download a track from the curated fallback CDN list."""
    urls = FALLBACK_MUSIC.get(channel_id, FALLBACK_MUSIC["informative"])

    for url in urls:
        cache_key = hashlib.md5(url.encode()).hexdigest()
        cached = os.path.join(MUSIC_CACHE_DIR, f"{cache_key}.mp3")

        if os.path.exists(cached):
            logger.info(f"Using cached fallback track: {cached}")
            _copy_file(cached, output_path)
            return output_path

        try:
            logger.info(f"Downloading fallback music track...")
            _download_file(url, cached)
            _copy_file(cached, output_path)
            logger.info(f"Background music saved: {output_path}")
            return output_path
        except Exception as e:
            logger.warning(f"Fallback download failed ({url}): {e}")
            continue

    logger.warning("All music sources failed — video will have no background music.")
    return None


def _download_file(url: str, dest: str) -> None:
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)


def _copy_file(src: str, dst: str) -> None:
    import shutil
    if src != dst:
        shutil.copy2(src, dst)
