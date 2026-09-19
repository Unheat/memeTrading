"""Automated YouTube video uploader for faceless forensic reels.

Uploads rendered MP4 video reels to YouTube (Unlisted or Public) via YouTube Data API v3.
Persists OAuth tokens to avoid repeated browser logins.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

logger = logging.getLogger(__name__)

# Standard YouTube Data API v3 OAuth scopes for video upload
YOUTUBE_UPLOAD_SCOPE = ["https://www.googleapis.com/auth/youtube.upload"]
DEFAULT_CLIENT_SECRETS_FILE = "client_secrets.json"
DEFAULT_TOKEN_FILE = ".youtube_token.json"
MAX_TITLE_LENGTH = 100
MAX_DESCRIPTION_LENGTH = 5000


@dataclass(frozen=True)
class YouTubeUploadResult:
    """Result of a YouTube video upload."""
    video_id: str
    url: str
    title: str
    privacy_status: str
    is_success: bool
    error: str | None = None


def is_google_api_installed() -> bool:
    """Check whether googleapiclient and google_auth_oauthlib are installed."""
    try:
        import google_auth_oauthlib  # noqa: F401
        import googleapiclient.discovery  # noqa: F401
        return True
    except ImportError:
        return False


def is_youtube_configured(
    secrets_path: Path | str | None = None,
    token_path: Path | str | None = None,
) -> bool:
    """Check whether credentials exist for unattended or interactive YouTube upload."""
    if not is_google_api_installed():
        return False

    sec_file = Path(secrets_path or os.getenv("YOUTUBE_CLIENT_SECRETS_FILE", DEFAULT_CLIENT_SECRETS_FILE))
    tok_file = Path(token_path or os.getenv("YOUTUBE_TOKEN_FILE", DEFAULT_TOKEN_FILE))
    has_secrets_env = bool(os.getenv("YOUTUBE_CLIENT_SECRETS_JSON"))

    return tok_file.exists() or sec_file.exists() or has_secrets_env


def extract_youtube_metadata(
    case_dir: Path | str,
    default_title: str | None = None,
) -> dict[str, Any]:
    """Extract optimized YouTube title, description, and hashtags from case artifacts.

    Args:
        case_dir: Path to case directory containing article.md and faceless/caption.txt.
        default_title: Optional fallback title if extraction fails.

    Returns:
        Dict containing title, description, and tags list.
    """
    case_path = Path(case_dir)
    caption_file = case_path / "faceless" / "caption.txt"
    article_file = case_path / "article.md"

    raw_caption = caption_file.read_text(encoding="utf-8") if caption_file.exists() else ""
    raw_article = article_file.read_text(encoding="utf-8") if article_file.exists() else ""

    # Extract title: Look for markdown h1 '# Title' in article, or first line in caption
    title = default_title or ""
    if not title and raw_article:
        for line in raw_article.splitlines():
            line_str = line.strip()
            if line_str.startswith("# "):
                title = line_str[2:].strip()
                break

    if not title and raw_caption:
        first_line = raw_caption.splitlines()[0].strip()
        title = first_line[:MAX_TITLE_LENGTH]

    if not title:
        title = f"Forensic Financial Audit - {case_path.name}"

    # Clamp title to YouTube limit
    title = title[:MAX_TITLE_LENGTH]

    # Extract tags / hashtags
    tags = ["finance", "forensic", "stocks", "investing", "sec", "short"]
    if raw_caption:
        found_tags = re.findall(r"#(\w+)", raw_caption)
        for tag in found_tags:
            t_clean = tag.lower().strip()
            if t_clean and t_clean not in tags:
                tags.append(t_clean)

    # Build description
    description_lines = []
    if raw_caption:
        description_lines.append(raw_caption.strip())
        description_lines.append("")

    description_lines.append("---")
    description_lines.append("DISCLAIMER: Educational financial research and forensic analysis only.")
    description_lines.append("Not investment advice or a solicitation to buy/sell securities.")
    description_lines.append("All figures audited directly from official SEC EDGAR regulatory filings.")
    description_lines.append("Read full forensic report with interactive receipts on our portal.")

    description = "\n".join(description_lines)[:MAX_DESCRIPTION_LENGTH]

    return {
        "title": title,
        "description": description,
        "tags": tags[:20],
    }


def get_authenticated_service(
    secrets_path: Path | str | None = None,
    token_path: Path | str | None = None,
) -> Any:
    """Authenticate and return an authorized YouTube Resource service.

    Args:
        secrets_path: Path to client_secrets.json.
        token_path: Path to stored token.json.

    Returns:
        Google API YouTube service object.

    Raises:
        RuntimeError: If dependencies or credentials are not configured.
    """
    if not is_google_api_installed():
        raise RuntimeError(
            "Google API libraries not installed. Install with: "
            "pip install google-api-python-client google-auth-oauthlib google-auth-httplib2"
        )

    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    tok_file = Path(token_path or os.getenv("YOUTUBE_TOKEN_FILE", DEFAULT_TOKEN_FILE))
    sec_file = Path(secrets_path or os.getenv("YOUTUBE_CLIENT_SECRETS_FILE", DEFAULT_CLIENT_SECRETS_FILE))
    secrets_json_env = os.getenv("YOUTUBE_CLIENT_SECRETS_JSON")

    creds: Any = None

    if tok_file.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(tok_file), YOUTUBE_UPLOAD_SCOPE)
        except Exception as exc:
            logger.warning("Failed loading credentials from %s: %s", tok_file, exc)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if secrets_json_env:
                client_config = json.loads(secrets_json_env)
                flow = InstalledAppFlow.from_client_config(client_config, YOUTUBE_UPLOAD_SCOPE)
            elif sec_file.exists():
                flow = InstalledAppFlow.from_client_secrets_file(str(sec_file), YOUTUBE_UPLOAD_SCOPE)
            else:
                raise RuntimeError(
                    f"No YouTube credentials found. Provide {sec_file} or set YOUTUBE_CLIENT_SECRETS_JSON."
                )

            creds = flow.run_local_server(port=0)

        # Save credentials for subsequent runs
        try:
            tok_file.write_text(creds.to_json(), encoding="utf-8")
        except Exception as exc:
            logger.warning("Failed to persist token to %s: %s", tok_file, exc)

    return build("youtube", "v3", credentials=creds)


def upload_reel_to_youtube(
    video_path: Path | str,
    title: str,
    description: str,
    tags: list[str] | None = None,
    privacy_status: str = "unlisted",
    secrets_path: Path | str | None = None,
    token_path: Path | str | None = None,
) -> YouTubeUploadResult:
    """Upload an MP4 video reel to YouTube.

    Args:
        video_path: Local path to the rendered MP4 file.
        title: YouTube video title.
        description: YouTube video description.
        tags: Optional list of keyword tags.
        privacy_status: "unlisted", "public", or "private".
        secrets_path: Optional path to client_secrets.json.
        token_path: Optional path to token.json.

    Returns:
        YouTubeUploadResult with video ID and URL.
    """
    video_file = Path(video_path)
    if not video_file.exists():
        return YouTubeUploadResult(
            video_id="",
            url="",
            title=title,
            privacy_status=privacy_status,
            is_success=False,
            error=f"Video file not found at {video_file}",
        )

    try:
        from googleapiclient.http import MediaFileUpload

        youtube = get_authenticated_service(secrets_path=secrets_path, token_path=token_path)

        body: dict[str, Any] = {
            "snippet": {
                "title": title[:MAX_TITLE_LENGTH],
                "description": description[:MAX_DESCRIPTION_LENGTH],
                "tags": tags or ["finance", "stocks", "sec"],
                "categoryId": "27",  # 27 = Education
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": False,
            },
        }

        media = MediaFileUpload(
            str(video_file.resolve()),
            mimetype="video/mp4",
            resumable=True,
        )

        logger.info("Starting YouTube upload for %s (privacy: %s)...", video_file.name, privacy_status)
        insert_request = youtube.videos().insert(
            part=",".join(body.keys()),
            body=body,
            media_body=media,
        )

        response: dict[str, Any] | None = None
        while response is None:
            status, response = insert_request.next_chunk()
            if status:
                logger.info("Uploaded %d%% to YouTube...", int(status.progress() * 100))

        video_id = response.get("id", "")
        url = f"https://www.youtube.com/watch?v={video_id}"
        logger.info("YouTube upload completed successfully! Video ID: %s, URL: %s", video_id, url)

        return YouTubeUploadResult(
            video_id=video_id,
            url=url,
            title=title,
            privacy_status=privacy_status,
            is_success=True,
        )
    except Exception as exc:
        logger.error("YouTube upload failed: %s", exc)
        return YouTubeUploadResult(
            video_id="",
            url="",
            title=title,
            privacy_status=privacy_status,
            is_success=False,
            error=str(exc),
        )
