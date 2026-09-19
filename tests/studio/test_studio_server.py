"""Unit tests for the Local Studio server and endpoints."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.studio.server import get_all_cases, get_studio_html


def test_get_all_cases(tmp_path: Path) -> None:
    """Verify scanning case folders extracts ticker, flags, and titles."""
    cases_root = tmp_path / "cases"
    cases_root.mkdir()

    case_1 = cases_root / "NVDA-2026-09-18-001"
    case_1.mkdir()
    (case_1 / "article.md").write_text("# NVDA Cloud Bottleneck Audit\nContent...", encoding="utf-8")
    (case_1 / "investigation.json").write_text(json.dumps({"ticker": "NVDA"}), encoding="utf-8")

    cases = get_all_cases(cases_root=str(cases_root))
    assert len(cases) == 1
    assert cases[0]["ticker"] == "NVDA"
    assert cases[0]["title"] == "NVDA Cloud Bottleneck Audit"
    assert cases[0]["has_article"] is True
    assert cases[0]["has_video"] is False


def test_get_studio_html() -> None:
    """Verify HTML interface includes critical controls and script tags."""
    html = get_studio_html()
    assert "MEMETRADING LOCAL STUDIO" in html
    assert "btn-run-article" in html
    assert "btn-run-all" in html
    assert "btn-publish-submit" in html
