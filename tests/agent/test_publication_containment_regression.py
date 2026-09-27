"""End-to-end containment regression tests.

Verifies that model-authored hallucinations (such as secret financing or cost assertions)
cannot reach memo.md, article.md, video reel, or public site artifacts when gates are unpassed
or claim ledger links are absent.
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest
from langchain_core.messages import AIMessage

from app.agent.runner import run_investigation
from app.agent.state import ResearchRequest
from app.cli.publish import publish_case
from app.media.cli import generate_video_for_case


class FabricatingModel:
    """Mock model returning fabricated financial claims in terminal text."""

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        content = str(getattr(messages[-1], "content", "")) if messages else ""
        if "Write an institutional" in content:
            return AIMessage(
                content="# Google Analysis\nGoogle secretly raised $40B in off-balance-sheet financing."
            )
        return AIMessage(
            content=(
                "Google secretly secured $40B in off-balance-sheet GPU financing from an offshore consortium, "
                "and internal TPU v6 costs are running at $1.20 per chip-hour with massive hidden liabilities."
            )
        )


def test_goog_shaped_containment_regression(tmp_path: Path):
    """Verify correct financials with failed gates/empty claims completely blocks all public artifacts."""
    req = ResearchRequest(query="Investigate GOOG valuation and cloud profitability", ticker="GOOG")

    result = run_investigation(
        request=req,
        model=FabricatingModel(),
        cases_root=tmp_path,
        generate_article=True,
        generate_video=True,
    )

    case_dir = tmp_path / result.case_id

    # 1. memo.md must exist as a safe audit artifact
    assert (case_dir / "memo.md").exists()
    memo_text = (case_dir / "memo.md").read_text(encoding="utf-8")

    # 2. Fabricated model narrative must be strictly excluded from memo.md
    assert "off-balance-sheet" not in memo_text
    assert "$40B" not in memo_text
    assert "$1.20" not in memo_text
    assert "massive hidden liabilities" not in memo_text
    assert (
        "Research validation incomplete" in memo_text
        or "Model-authored narrative claims without an explicit evidence link are excluded" in memo_text
    )

    # 3. article.md and faceless video reel must be completely blocked
    assert not (case_dir / "article.md").exists()
    assert result.article_markdown is None
    assert not (case_dir / "faceless" / "dialogue.json").exists()

    # 4. investigation.json records blocked publication readiness and raw text for diagnostics only
    inv_data = json.loads((case_dir / "investigation.json").read_text(encoding="utf-8"))
    assert inv_data["publication_readiness"]["status"] == "blocked"
    assert len(inv_data["publication_readiness"]["reasons"]) > 0
    assert "diagnostic_terminal_model_text" in inv_data
    assert "$40B" in inv_data["diagnostic_terminal_model_text"]

    # 5. External CLI publisher must reject the case
    with pytest.raises(ValueError, match="blocked from publication"):
        publish_case(case_dir=case_dir, web_root=tmp_path / "web", youtube_upload=False, deploy=False)

    # 6. Standalone video CLI must reject the case
    with pytest.raises(ValueError, match="blocked from video generation"):
        generate_video_for_case(case_dir=case_dir, script_only=True)
