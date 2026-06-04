"""
uploader.py
───────────
Uploads a rendered video to YouTube using the YouTube Data API v3.

Only runs when `auto_upload: true` is set for a channel in config.yaml.
OAuth2 credentials are loaded from a file path specified in .env —
your client_secrets.json is NEVER hardcoded.

First-time setup: run this file directly to complete OAuth2 flow.
After that, a token file is saved locally and reused automatically.
"""

import logging
import os
import pickle
from pathlib import Path

from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

load_dotenv()
logger = logging.getLogger(__name__)

# YouTube API scope — upload-only
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN_FILE = ".youtube_token.pickle"


def _get_youtube_service():
    """
    Authenticate with YouTube via OAuth2 and return a service object.
    Uses saved token if available; otherwise opens browser for auth.
    """
    secrets_file = os.getenv("YOUTUBE_CLIENT_SECRETS_FILE", "client_secrets.json")

    if not os.path.exists(secrets_file):
        raise FileNotFoundError(
            f"YouTube client secrets file not found: '{secrets_file}'\n"
            "Download it from Google Cloud Console → APIs & Services → Credentials\n"
            "and set YOUTUBE_CLIENT_SECRETS_FILE in your .env file."
        )

    creds = None

    # Load cached token
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "rb") as f:
            creds = pickle.load(f)

    # Refresh or re-authenticate
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(secrets_file, SCOPES)
            creds = flow.run_local_server(port=0)

        # Save token for next run
        with open(TOKEN_FILE, "wb") as f:
            pickle.dump(creds, f)
        logger.info(f"YouTube OAuth token saved to {TOKEN_FILE}")

    return build("youtube", "v3", credentials=creds)


def upload_to_youtube(
    video_path: str,
    title: str,
    description: str,
    hashtags: list[str],
    channel_name: str,
    privacy: str = "private",  # "private" | "unlisted" | "public"
) -> str:
    """
    Upload a video to YouTube.

    Args:
        video_path   : Path to the .mp4 file.
        title        : Video title.
        description  : Video description.
        hashtags     : List of hashtag strings (without #).
        channel_name : Human-readable channel name (for logging).
        privacy      : Upload privacy status.

    Returns:
        YouTube video ID of the uploaded video.
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")

    youtube = _get_youtube_service()

    # Format hashtags for description
    tag_str = " ".join(f"#{h.lstrip('#')}" for h in hashtags)
    full_description = f"{description}\n\n{tag_str}"

    body = {
        "snippet": {
            "title": title[:100],  # YouTube limit
            "description": full_description[:5000],
            "tags": [h.lstrip("#") for h in hashtags],
            "categoryId": "22",  # People & Blogs (suitable for informative/gaming)
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        video_path,
        mimetype="video/mp4",
        resumable=True,
        chunksize=5 * 1024 * 1024,  # 5MB chunks
    )

    logger.info(f"Uploading '{title}' to YouTube (channel: {channel_name})...")

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            logger.info(f"Upload progress: {pct}%")

    video_id = response["id"]
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    logger.info(f"✅ Upload complete! Video ID: {video_id}")
    logger.info(f"   URL: {video_url}")
    return video_id


if __name__ == "__main__":
    """
    Run this file directly to complete YouTube OAuth2 setup.
    Only needed once — the token is saved and reused automatically.
    """
    logging.basicConfig(level=logging.INFO)
    print("Starting YouTube OAuth2 setup...")
    svc = _get_youtube_service()
    print("✅ YouTube authentication successful! Token saved.")
    print("You can now use auto_upload: true in config.yaml")
