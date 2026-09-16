"""Tests for the end-to-end investigation runner."""
from pathlib import Path
import pytest
from langchain_core.messages import AIMessage
from app.agent.runner import run_investigation, InvestigationResult
from app.agent.state import BudgetLimits, ResearchRequest
from app.config import AppConfig, ResearchConfig


class FakeRunnerModel:
    """Offline test model that immediately returns a conclusion."""

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        return AIMessage(content="Final forensic conclusion: speculation unsupported.")


def test_run_investigation_generates_case_artifacts(tmp_path):
    req = ResearchRequest(query="Give an investment recommendation for TEST", ticker="TEST", company="Test Corp")
    result = run_investigation(request=req, model=FakeRunnerModel(), cases_root=tmp_path)

    assert isinstance(result, InvestigationResult)
    assert result.ticker == "TEST"
    assert result.status == "insufficient_evidence"
    assert "NO_POSITION" in result.memo_markdown

    # Verify disk files created under tmp_path/case_<id>/
    case_dir = tmp_path / result.case_id
    assert case_dir.exists()
    assert (case_dir / "memo.md").exists()
    assert (case_dir / "investigation.json").exists()
    assert (case_dir / "run-manifest.json").exists()
    assert not (case_dir / "article.md").exists()
    assert not (case_dir / "faceless").exists()

    memo_content = (case_dir / "memo.md").read_text(encoding="utf-8")
    assert "# Research Incomplete: $TEST" in memo_content


def test_run_investigation_with_rick_morty_character_pair(tmp_path):
    """Verify run_investigation cleanly passes rick_morty character pair to media generator."""
    import json
    req = ResearchRequest(query="Give an investment recommendation for RICK", ticker="RICK")
    result = run_investigation(
        request=req,
        model=FakeRunnerModel(),
        cases_root=tmp_path,
        character_pair="rick_morty",
    )
    case_dir = tmp_path / result.case_id
    assert result.status == "insufficient_evidence"
    assert not (case_dir / "faceless" / "dialogue.json").exists()
    assert not (case_dir / "article.md").exists()


def test_run_investigation_applies_configured_research_budget(tmp_path):
    """Verify default request budget is replaced by config.yaml research limits."""
    config = AppConfig(
        research=ResearchConfig(
            max_tool_calls=42,
            max_identical_calls=4,
            cases_root=str(tmp_path),
        )
    )
    result = run_investigation(
        request=ResearchRequest(query="Investigate configured budget", ticker="CFG"),
        model=FakeRunnerModel(),
        generate_media=False,
        config=config,
    )

    assert result.final_state["budget_state"]["max_tool_calls"] == 42
    assert result.final_state["budget_state"]["max_identical_calls"] == 4
