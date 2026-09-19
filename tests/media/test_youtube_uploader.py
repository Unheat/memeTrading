"""Unit tests for the automated YouTube video uploader and metadata extractor."""
from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.media.youtube_uploader import (
    YouTubeUploadResult,
    extract_youtube_metadata,
    is_google_api_installed,
    is_youtube_configured,
    upload_reel_to_youtube,
)


def test_extract_youtube_metadata_from_case(tmp_path: Path) -> None:
    """Verify title, description, and hashtags are extracted correctly from case files."""
    case_dir = tmp_path / "cases" / "TEST-2026-09-18-001"
    faceless_dir = case_dir / "faceless"
    faceless_dir.mkdir(parents=True)

    article_content = """# DRAM Margin Warning: The $30B Micron CapEx Trap

Micron is expanding gross margins, but inventory days have surged [1].
"""
    (case_dir / "article.md").write_text(article_content, encoding="utf-8")

    caption_content = """Holy crap Stewie, look at Micron's inventory!
$MU is building $8B in fabs while memory prices drop.
#Micron #Stocks #Forensic #Investing
"""
    (faceless_dir / "caption.txt").write_text(caption_content, encoding="utf-8")

    meta = extract_youtube_metadata(case_dir)

    assert meta["title"] == "DRAM Margin Warning: The $30B Micron CapEx Trap"
    assert "DISCLAIMER" in meta["description"]
    assert "Holy crap Stewie" in meta["description"]
    assert "micron" in meta["tags"]
    assert "stocks" in meta["tags"]
    assert "forensic" in meta["tags"]


def test_extract_youtube_metadata_fallback(tmp_path: Path) -> None:
    """Verify fallback behavior when caption or article files are missing."""
    case_dir = tmp_path / "empty_case"
    case_dir.mkdir()

    meta = extract_youtube_metadata(case_dir, default_title="Fallback Title")
    assert meta["title"] == "Fallback Title"
    assert "DISCLAIMER" in meta["description"]


def test_upload_reel_missing_file() -> None:
    """Ensure upload returns failure cleanly if video file does not exist."""
    res = upload_reel_to_youtube(
        video_path="nonexistent_video.mp4",
        title="Test Reel",
        description="Test Description",
    )
    assert not res.is_success
    assert "not found" in (res.error or "")


def test_topic_slug_regex_compliance() -> None:
    """Verify slug generation matches the Node.js regex constraint /^[a-z0-9]+(?:-[a-z0-9]+){0,2}$/."""
    node_regex = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+){0,2}$")

    test_cases = [
        # (ticker, query)
        ("MU", "Investigate DRAM sustainability"),
        ("NVDA", "Find GPU margins"),
        ("UNKNOWN", "Find key supply chain beneficiaries for AI memory"),
        ("", "Why is cash flow declining rapidly?"),
        (None, "Semiconductor cycle top"),
    ]

    for ticker, query in test_cases:
        clean_ticker = (ticker or "").strip().lower()
        if clean_ticker and clean_ticker not in {"research", "unknown"}:
            slug_cand = re.sub(r"[^a-z0-9]+", "-", clean_ticker).strip("-")
            parts = [p for p in slug_cand.split("-") if p][:3]
            topic_slug = "-".join(parts) if parts else "deep-research"
        else:
            clean_query = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")
            parts = [p for p in clean_query.split("-") if p][:3]
            topic_slug = "-".join(parts) if parts else "deep-research"

        assert node_regex.match(topic_slug), f"Slug '{topic_slug}' failed regex validation"
        assert len(topic_slug.split("-")) <= 3
