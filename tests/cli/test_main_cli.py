"""End-to-end CLI tests for main.py."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from main import _resolve_media_flags, main
from app.agent.runner import InvestigationResult


def test_resolve_media_flags_article_only() -> None:
    """--article flag enables article generation only, suppressing video and rendering."""
    args = argparse.Namespace(
        article=True,
        video=False,
        video_script_only=False,
        article_video=False,
    )
    gen_article, gen_video, render = _resolve_media_flags(args)
    assert gen_article is True
    assert gen_video is False
    assert render is False


def test_resolve_media_flags_default_no_media() -> None:
    """Default invocation has all media generation flags disabled."""
    args = argparse.Namespace(
        article=False,
        video=False,
        video_script_only=False,
        article_video=False,
    )
    gen_article, gen_video, render = _resolve_media_flags(args)
    assert gen_article is False
    assert gen_video is False
    assert render is False


def test_resolve_media_flags_video_script_only() -> None:
    """--video-script-only enables article and video script without video rendering."""
    args = argparse.Namespace(
        article=False,
        video=False,
        video_script_only=True,
        article_video=False,
    )
    gen_article, gen_video, render = _resolve_media_flags(args)
    assert gen_article is True
    assert gen_video is True
    assert render is False


def test_resolve_media_flags_video_full() -> None:
    """--video enables article, video script, and full video rendering."""
    args = argparse.Namespace(
        article=False,
        video=True,
        video_script_only=False,
        article_video=False,
    )
    gen_article, gen_video, render = _resolve_media_flags(args)
    assert gen_article is True
    assert gen_video is True
    assert render is True


def test_main_cli_e2e_article_flag_no_video(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """Verify main() CLI invokes run_investigation with generate_article=True, generate_video=False."""
    case_id = "RESEARCH-2026-09-27-001"
    case_dir = tmp_path / case_id
    case_dir.mkdir(parents=True)
    (case_dir / "memo.md").write_text("# Test Memo\nTop picks: NVDA 55%, TSM 45%.", encoding="utf-8")
    (case_dir / "investigation.json").write_text("{}", encoding="utf-8")
    (case_dir / "article.md").write_text("# Test Article [1]\nCited claims [1].", encoding="utf-8")

    mock_result = InvestigationResult(
        case_id=case_id,
        ticker=None,
        status="completed",
        memo_markdown="# Test Memo",
        article_markdown="# Test Article [1]",
        final_state={"status": "completed"},
    )

    test_args = [
        "main.py",
        "--query", "Find best 2 tech stocks in AI",
        "--article",
    ]

    with patch.object(sys, "argv", test_args), \
         patch("main.load_config") as mock_cfg, \
         patch("main.run_investigation", return_value=mock_result) as mock_run:

        cfg_mock = MagicMock()
        cfg_mock.research.cases_root = str(tmp_path)
        cfg_mock.llm.model = "test-model"
        cfg_mock.media.character_pair = "peter_stewie"
        mock_cfg.return_value = cfg_mock

        exit_code = main()

        assert exit_code == 0
        mock_run.assert_called_once()
        kwargs = mock_run.call_args.kwargs
        assert kwargs["generate_article"] is True
        assert kwargs["generate_video"] is False
        assert kwargs["render_video"] is False
        assert kwargs["request"].query == "Find best 2 tech stocks in AI"

        captured = capsys.readouterr()
        assert "PROMPT-FIRST DEEP RESEARCH AGENT" in captured.out
        assert "Article:   " in captured.out
        assert "Video Reel" not in captured.out
        assert "Deep Research Completed" in captured.out
        assert "article.md" in captured.out
