"""Unit tests for standalone video generation CLI and publication gates."""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from app.media.cli import generate_video_for_case


def test_generate_video_for_case_requires_investigation_json(tmp_path: Path) -> None:
    """Standalone video generation fails immediately if investigation.json is missing."""
    case_dir = tmp_path / "NO_JSON-2026-09-18-001"
    case_dir.mkdir(parents=True)
    (case_dir / "article.md").write_text("# Title\nValid content [1].", encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="investigation.json not found"):
        generate_video_for_case(case_dir=case_dir, script_only=True)


def test_generate_video_for_case_blocked_when_not_publishable(tmp_path: Path) -> None:
    """Standalone video generation rejects unpublishable / unvalidated investigations."""
    case_dir = tmp_path / "BLOCKED-2026-09-18-001"
    case_dir.mkdir(parents=True)
    (case_dir / "article.md").write_text("# Title\nValid content [1].", encoding="utf-8")

    inv_data = {
        "ticker": "BLK",
        "publication_readiness": {
            "passed": False,
            "status": "blocked",
            "reasons": ["evidence_gate did not pass"],
        },
        "citation_cards": [{"index": 1, "title": "SEC 10-K", "url": "https://sec.gov"}],
    }
    (case_dir / "investigation.json").write_text(json.dumps(inv_data), encoding="utf-8")

    with pytest.raises(ValueError, match="blocked from video generation"):
        generate_video_for_case(case_dir=case_dir, script_only=True)


def test_generate_video_for_case_requires_article_md(tmp_path: Path) -> None:
    """Standalone video generation cannot fall back to memo.md; article.md is mandatory."""
    case_dir = tmp_path / "NO_ARTICLE-2026-09-18-001"
    case_dir.mkdir(parents=True)
    (case_dir / "memo.md").write_text("# Memo\nValid content.", encoding="utf-8")

    inv_data = {
        "ticker": "NOART",
        "publication_readiness": {"passed": True, "status": "publishable", "reasons": []},
        "citation_cards": [{"index": 1, "title": "SEC 10-K", "url": "https://sec.gov"}],
    }
    (case_dir / "investigation.json").write_text(json.dumps(inv_data), encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="article.md not found"):
        generate_video_for_case(case_dir=case_dir, script_only=True)


def test_generate_video_for_case_validates_article_citations(tmp_path: Path) -> None:
    """Standalone video generation rejects article.md with invalid/dangling citations."""
    case_dir = tmp_path / "INVALID_CITE-2026-09-18-001"
    case_dir.mkdir(parents=True)
    (case_dir / "article.md").write_text("# Title\nDangling citation [99].", encoding="utf-8")

    inv_data = {
        "ticker": "INVCITE",
        "publication_readiness": {"passed": True, "status": "publishable", "reasons": []},
        "citation_cards": [{"index": 1, "title": "SEC 10-K", "url": "https://sec.gov"}],
    }
    (case_dir / "investigation.json").write_text(json.dumps(inv_data), encoding="utf-8")

    with pytest.raises(ValueError, match="article failed citation validation"):
        generate_video_for_case(case_dir=case_dir, script_only=True)


def test_generate_video_for_case_ignores_appended_bibliography(tmp_path: Path, monkeypatch) -> None:
    """The persisted article's trailing bibliography must not fail the video citation gate.

    Bibliography entries are the sources themselves and carry no [n] tags; the gate must
    validate the same body the writer validated, not the full persisted file.
    """
    case_dir = tmp_path / "BIBLIO-2026-09-28-001"
    case_dir.mkdir(parents=True)
    article = (
        "# Title\n\nRevenue grew by 15% [1].\n\n---\n\n"
        "## Primary Sources & Regulatory Receipts\n\n"
        "1. **U.S. Securities & Exchange Commission (SEC) — Official XBRL Financial Statements** "
        "(SEC Accession `sec_xbrl` | [Official Source](https://www.sec.gov))\n"
    )
    (case_dir / "article.md").write_text(article, encoding="utf-8")
    inv_data = {
        "ticker": "BIBLIO",
        "publication_readiness": {"passed": True, "status": "publishable", "reasons": []},
        "citation_cards": [{"index": 1, "title": "SEC 10-K", "url": "https://sec.gov"}],
    }
    (case_dir / "investigation.json").write_text(json.dumps(inv_data), encoding="utf-8")

    captured: dict[str, object] = {}

    def fake_generate_reel_script(article_markdown: str, model: object, character_pair: str, reel_temperature: float) -> tuple[list[dict], str, str]:
        captured["article"] = article_markdown
        return [], "script", "caption"

    monkeypatch.setattr("app.media.cli.generate_reel_script", fake_generate_reel_script)
    result = generate_video_for_case(case_dir=case_dir, script_only=True)
    assert result is None
    assert "Primary Sources" not in str(captured.get("article", ""))
