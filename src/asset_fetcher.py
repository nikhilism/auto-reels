"""
asset_fetcher.py
────────────────
Downloads vertical (portrait) background video clips from the Pexels API.

API key is loaded from .env — never hardcoded.
Clips are cached in temp/ to avoid re-downloading the same file.
"""

import os
import hashlib
import logging
import requests
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

PEXELS_VIDEO_ENDPOINT = "https://api.pexels.com/videos/search"
CACHE_DIR = "temp/pexels_cache"


def _get_api_key() -> str:
    key = os.getenv("PEXELS_API_KEY")
    if not key:
        raise EnvironmentError(
            "PEXELS_API_KEY is not set. "
            "Copy .env.example to .env and add your key."
        )
    return key


def _cache_path(query: str, index: int) -> str:
    """Generate a unique cache filename for a query+index combination."""
    safe = hashlib.md5(f"{query}_{index}".encode()).hexdigest()
    return os.path.join(CACHE_DIR, f"{safe}.mp4")


def fetch_background_video(
    queries: list[str],
    output_path: str,
    orientation: str = "portrait",
    min_duration: int = 10,
    max_results_per_query: int = 10,
) -> str:
    """
    Search Pexels for a background video clip and download it.

    Tries each query in order until a suitable vertical video is found.
    Uses a local cache so repeated runs don't re-download.

    Args:
        queries             : List of search terms (from Gemini output).
        output_path         : Where to save the downloaded .mp4.
        orientation         : "portrait" for 9:16 vertical video.
        min_duration        : Minimum clip length in seconds.
        max_results_per_query: How many results to check per query.

    Returns:
        Path to the downloaded video file.
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    api_key = _get_api_key()
    headers = {"Authorization": api_key}

    for query in queries:
        logger.info(f"Searching Pexels for: '{query}'")
        params = {
            "query": query,
            "orientation": orientation,
            "size": "medium",
            "per_page": max_results_per_query,
        }

        try:
            resp = requests.get(
                PEXELS_VIDEO_ENDPOINT,
                headers=headers,
                params=params,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            logger.warning(f"Pexels request failed for '{query}': {e}")
            continue

        videos = data.get("videos", [])
        if not videos:
            logger.warning(f"No results for query: '{query}'")
            continue

        for video in videos:
            duration = video.get("duration", 0)
            if duration < min_duration:
                continue

            # Pick the best quality vertical video file
            video_files = video.get("video_files", [])
            best_file = _pick_best_vertical_file(video_files)
            if not best_file:
                continue

            video_url = best_file["link"]
            video_id = video["id"]

            # Check cache first
            cached = _cache_path(query, video_id)
            if os.path.exists(cached):
                logger.info(f"Using cached clip: {cached}")
                _copy_file(cached, output_path)
                return output_path

            # Download
            logger.info(
                f"Downloading Pexels video {video_id} "
                f"({duration}s, {best_file.get('width')}x{best_file.get('height')})"
            )
            try:
                _download_file(video_url, cached)
                _copy_file(cached, output_path)
                logger.info(f"Background video saved: {output_path}")
                return output_path
            except Exception as e:
                logger.warning(f"Download failed for video {video_id}: {e}")
                continue

    raise RuntimeError(
        f"Could not find a suitable background video for queries: {queries}"
    )


def _pick_best_vertical_file(video_files: list) -> dict | None:
    """
    From a list of Pexels video file objects, pick the best vertical one.
    Prefers HD (1080p or 720p) portrait files.
    """
    portrait_files = [
        f for f in video_files
        if f.get("height", 0) > f.get("width", 1)  # height > width = portrait
    ]

    if not portrait_files:
        # Fall back to any file — we'll crop it in video_editor.py
        portrait_files = video_files

    # Sort by resolution (prefer higher quality but not 4K)
    def quality_score(f):
        h = f.get("height", 0)
        if h >= 1920:
            return 1  # 4K — avoid (too large to download quickly)
        return h

    portrait_files.sort(key=quality_score, reverse=True)
    return portrait_files[0] if portrait_files else None


def _download_file(url: str, dest_path: str) -> None:
    """Stream-download a file to dest_path."""
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)


def _copy_file(src: str, dst: str) -> None:
    """Copy a file from src to dst."""
    import shutil
    if src != dst:
        shutil.copy2(src, dst)
