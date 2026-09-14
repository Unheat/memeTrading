"""Tests for the end-to-end investigation runner."""
from pathlib import Path
import pytest
from langchain_core.messages import AIMessage
from app.agent.runner import run_investigation, InvestigationResult
from app.agent.state import ResearchRequest


class FakeRunnerModel:
    """Offline test model that immediately returns a conclusion."""

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        return AIMessage(content="Final forensic conclusion: speculation unsupported.")


def test_run_investigation_generates_case_artifacts(tmp_path):
    req = ResearchRequest(query="Investigate $TEST hype", ticker="TEST", company="Test Corp")
    result = run_investigation(request=req, model=FakeRunnerModel(), cases_root=tmp_path)

    assert isinstance(result, InvestigationResult)
    assert result.ticker == "TEST"
    assert result.status == "completed"
    assert "speculation unsupported" in result.memo_markdown

    # Verify disk files created under tmp_path/case_<id>/
    case_dir = tmp_path / result.case_id
    assert case_dir.exists()
    assert (case_dir / "memo.md").exists()
    assert (case_dir / "investigation.json").exists()
    assert (case_dir / "article.md").exists()
    assert (case_dir / "faceless" / "dialogue.json").exists()
    assert (case_dir / "faceless" / "caption.txt").exists()

    memo_content = (case_dir / "memo.md").read_text(encoding="utf-8")
    assert "# Meme Market Forensic Memo: $TEST" in memo_content
