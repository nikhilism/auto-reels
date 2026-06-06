"""
asset_fetcher.py
────────────────
Downloads vertical (portrait) background video clips from the Pexels API.

API key is loaded from .env — never hardcoded.
Clips are cached in temp/pexels_cache/ to avoid re-downloading.

fetch_multiple_clips() returns 3-4 distinct clips from different queries,
giving the video editor variety to create tasteful scene transitions.
"""

import os
import hashlib
import logging
import requests
import shutil
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


def _cache_path(query: str, video_id: int) -> str:
    safe = hashlib.md5(f"{query}_{video_id}".encode()).hexdigest()
    return os.path.join(CACHE_DIR, f"{safe}.mp4")


def fetch_multiple_clips(
    queries: list[str],
    output_dir: str,
    count: int = 4,
    min_duration: int = 12,
) -> list[str]:
    """
    Fetch multiple distinct background video clips from Pexels.
    Each clip comes from a different query for maximum visual variety.

    Args:
        queries     : List of search terms (Gemini-generated + channel fallbacks).
        output_dir  : Directory to save downloaded clips.
        count       : How many clips to fetch (default: 4).
        min_duration: Minimum clip length in seconds.

    Returns:
        List of local .mp4 file paths (may be fewer than count if not enough results).
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    api_key = _get_api_key()
    headers = {"Authorization": api_key}
    used_video_ids: set[int] = set()
    clips: list[str] = []

    # Use diverse queries — spread across the list
    # Interleave AI-generated and fallback queries for variety
    selected_queries = _pick_diverse_queries(queries, count)

    for i, query in enumerate(selected_queries):
        output_path = os.path.join(output_dir, f"clip_{i:02d}.mp4")
        clip = _fetch_single_clip(
            query=query,
            output_path=output_path,
            headers=headers,
            used_video_ids=used_video_ids,
            min_duration=min_duration,
        )
        if clip:
            clips.append(clip)
            logger.info(f"Clip {i+1}/{count} ready: {os.path.basename(clip)}")
        else:
            logger.warning(f"Could not find a clip for query: '{query}'")

    if not clips:
        raise RuntimeError(
            f"Could not fetch any background clips. Queries tried: {selected_queries}"
        )

    logger.info(f"Fetched {len(clips)} background clips.")
    return clips


def _pick_diverse_queries(queries: list[str], count: int) -> list[str]:
    """
    Pick `count` queries spread across the full list for variety.
    Avoids picking the same query twice.
    """
    if len(queries) <= count:
        return queries[:count]

    # Step through the list evenly
    step = len(queries) / count
    selected = []
    for i in range(count):
        idx = int(i * step)
        selected.append(queries[idx])
    return selected


def _fetch_single_clip(
    query: str,
    output_path: str,
    headers: dict,
    used_video_ids: set,
    min_duration: int = 12,
    max_results: int = 15,
) -> str | None:
    """Search Pexels for a single portrait clip not already used."""
    logger.info(f"Searching Pexels: '{query}'")
    params = {
        "query": query,
        "orientation": "portrait",
        "size": "medium",
        "per_page": max_results,
    }

    try:
        resp = requests.get(
            PEXELS_VIDEO_ENDPOINT,
            headers=headers,
            params=params,
            timeout=15,
        )
        resp.raise_for_status()
        videos = resp.json().get("videos", [])
    except requests.RequestException as e:
        logger.warning(f"Pexels request failed for '{query}': {e}")
        return None

    if not videos:
        return None

    for video in videos:
        vid_id = video.get("id")
        duration = video.get("duration", 0)

        if vid_id in used_video_ids:
            continue
        if duration < min_duration:
            continue

        best_file = _pick_best_vertical_file(video.get("video_files", []))
        if not best_file:
            continue

        # Check cache
        cached = _cache_path(query, vid_id)
        if os.path.exists(cached):
            logger.info(f"Using cached clip (Pexels #{vid_id})")
            shutil.copy2(cached, output_path)
            used_video_ids.add(vid_id)
            return output_path

        # Download
        logger.info(
            f"Downloading Pexels #{vid_id} ({duration}s, "
            f"{best_file.get('width')}x{best_file.get('height')}) — '{query}'"
        )
        try:
            _download_file(best_file["link"], cached)
            shutil.copy2(cached, output_path)
            used_video_ids.add(vid_id)
            return output_path
        except Exception as e:
            logger.warning(f"Download failed for video {vid_id}: {e}")
            continue

    return None


# ── Legacy single-clip function (kept for backward compat) ─────────────────────
def fetch_background_video(
    queries: list[str],
    output_path: str,
    orientation: str = "portrait",
    min_duration: int = 10,
    max_results_per_query: int = 10,
) -> str:
    """Fetch a single background video (legacy interface)."""
    temp_dir = os.path.dirname(output_path)
    clips = fetch_multiple_clips(queries, temp_dir, count=1, min_duration=min_duration)
    if clips:
        shutil.copy2(clips[0], output_path)
        return output_path
    raise RuntimeError(f"Could not find a background video for queries: {queries}")


def _pick_best_vertical_file(video_files: list) -> dict | None:
    portrait = [
        f for f in video_files
        if f.get("height", 0) > f.get("width", 1)
    ]
    if not portrait:
        portrait = video_files

    def quality_score(f):
        h = f.get("height", 0)
        if h >= 1920:
            return 1  # Prefer not 4K (slow to download)
        return h

    portrait.sort(key=quality_score, reverse=True)
    return portrait[0] if portrait else None


def _download_file(url: str, dest_path: str) -> None:
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
