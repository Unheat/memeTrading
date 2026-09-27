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
    # Default: no article or video generated
    assert not (case_dir / "article.md").exists()
    assert not (case_dir / "faceless").exists()

    memo_content = (case_dir / "memo.md").read_text(encoding="utf-8")
    assert "# Research Incomplete: $TEST" in memo_content


def test_run_investigation_default_no_media(tmp_path):
    """Default run produces only core artifacts (no article, no video)."""
    req = ResearchRequest(query="Investigate LEAN", ticker="LEAN")
    result = run_investigation(request=req, model=FakeRunnerModel(), cases_root=tmp_path)

    case_dir = tmp_path / result.case_id
    assert (case_dir / "memo.md").exists()
    assert not (case_dir / "article.md").exists()
    assert not (case_dir / "faceless" / "dialogue.json").exists()


def test_run_investigation_with_article_flag_blocked_when_insufficient_evidence(tmp_path):
    """Passing generate_article=True does not write article.md when publication readiness is blocked."""
    class ArticleModel:
        def bind_tools(self, tools):
            return self
        def invoke(self, messages):
            return AIMessage(content="Final forensic conclusion.")

    req = ResearchRequest(query="Investigate ART", ticker="ART")
    result = run_investigation(
        request=req, model=ArticleModel(), cases_root=tmp_path, generate_article=True,
    )

    case_dir = tmp_path / result.case_id
    assert not (case_dir / "article.md").exists()
    assert result.article_markdown is None
    assert result.final_state["publication_readiness"]["status"] == "blocked"


def test_run_investigation_with_article_flag_publishable(tmp_path, monkeypatch):
    """Passing generate_article=True writes article.md when publication readiness passes."""
    class ArticleModel:
        def bind_tools(self, tools):
            return self
        def invoke(self, messages):
            content = str(getattr(messages[-1], "content", "")) if messages else ""
            if "Write an institutional" in content:
                return AIMessage(content="# Cited Article\nOfficial filings confirm revenue growth [1].")
            return AIMessage(content="Final forensic conclusion.")

    from langgraph.graph.state import CompiledStateGraph

    orig_invoke = CompiledStateGraph.invoke
    def mock_invoke(self, state, config=None):
        out = dict(orig_invoke(self, state, config=config))
        out["status"] = "completed"
        out["evidence"] = [{
            "form": "10-K",
            "accession": "0000000000-26-000001",
            "source_url": "https://www.sec.gov/Archives/edgar/data/123/000000000026000001/doc.htm",
            "quote": "Revenue grew 15% year-over-year.",
        }]
        out["evidence_gate"] = {"passed": True}
        out["accounting_gate"] = {"passed": True}
        out["valuation_gate"] = {"passed": True}
        out["asymmetry_gate"] = {"passed": True}
        return out

    monkeypatch.setattr(CompiledStateGraph, "invoke", mock_invoke)

    req = ResearchRequest(query="Investigate ART", ticker="ART")
    result = run_investigation(
        request=req, model=ArticleModel(), cases_root=tmp_path, generate_article=True,
    )

    case_dir = tmp_path / result.case_id
    assert (case_dir / "article.md").exists()
    article_content = (case_dir / "article.md").read_text(encoding="utf-8")
    assert "[1]" in article_content
    assert result.article_markdown is not None
    assert result.final_state["publication_readiness"]["status"] == "publishable"


def test_run_investigation_with_rick_morty_character_pair(tmp_path):
    """Verify run_investigation cleanly passes rick_morty character pair."""
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
        config=config,
    )

    assert result.final_state["budget_state"]["max_tool_calls"] == 42
    assert result.final_state["budget_state"]["max_identical_calls"] == 4


def test_run_investigation_legacy_generate_media_false(tmp_path):
    """Legacy generate_media=False suppresses all media."""
    req = ResearchRequest(query="Legacy test", ticker="LEG")
    result = run_investigation(
        request=req, model=FakeRunnerModel(), cases_root=tmp_path, generate_media=False,
    )
    case_dir = tmp_path / result.case_id
    assert not (case_dir / "article.md").exists()
    assert not (case_dir / "faceless").exists()


def test_run_investigation_multi_candidate_e2e_up_to_article_no_video(tmp_path, monkeypatch):
    """E2E test: multi-candidate run with generate_article=True produces article.md with allocations, without video."""
    from langgraph.graph.state import CompiledStateGraph
    import json

    class MultiCandidateArticleModel:
        def __init__(self):
            self.captured_prompts = []

        def bind_tools(self, tools):
            return self

        def invoke(self, messages):
            content = str(getattr(messages[-1], "content", "")) if messages else ""
            self.captured_prompts.append(content)
            if "Write an institutional" in content:
                # Article writer model response citing [1] and [2] and featuring top picks
                return AIMessage(content="""# The AI Silicon Duopoly: NVDA & TSM Allocation Thesis

*Institutional audit of leading semiconductor infrastructure providers establishes an asymmetric risk/reward opportunity.*

> ### Executive Briefing
> - **Top Allocation**: NVIDIA ($NVDA) captured at 55% portfolio weighting.[1]
> - **Foundry Monopoly**: Taiwan Semiconductor ($TSM) sized at 45% weighting.[2]

## I. Supply Chain Disconnect
Official filings confirm NVIDIA data center revenue expanded significantly [1].
Meanwhile, TSMC manufactures over 90% of sub-5nm advanced compute silicon [2].

| Ticker | Portfolio Allocation | Target Upside |
| :--- | :--- | :--- |
| **NVDA** | 55% [1] | +67.2% [1] |
| **TSM** | 45% [2] | +42.0% [2] |

The Investment Committee formally directs execution of this dual allocation [1, 2].
""")
            # Research terminal model decision
            return AIMessage(content="""## Executive Decision

| Rank | Ticker | Allocation | 12-Mo Target | Asymmetry Ratio | Rationale |
| --- | --- | --- | --- | --- | --- |
| #1 | NVDA | 55% | $376.32 | 3.2x | Monopolistic CUDA datacenter ecosystem and Blackwell compute ramps |
| #2 | TSM | 45% | $550.00 | 2.6x | Irreplaceable foundry monopoly for sub-5nm accelerators |
""")

    orig_invoke = CompiledStateGraph.invoke

    def mock_invoke(self, state, config=None):
        out = dict(orig_invoke(self, state, config=config))
        out["status"] = "completed"
        out["candidates"] = {
            "cand_nvda": {
                "ticker": "NVDA",
                "company": "NVIDIA Corp",
                "evidence": [{
                    "form": "10-K",
                    "accession": "0001045810-26-000010",
                    "source_url": "https://www.sec.gov/Archives/edgar/data/1045810/000104581026000010/nvda.htm",
                    "quote": "Compute and Networking revenue grew 150% year-over-year.",
                }],
            },
            "cand_tsm": {
                "ticker": "TSM",
                "company": "Taiwan Semiconductor",
                "evidence": [{
                    "form": "20-F",
                    "accession": "0001628280-26-000020",
                    "source_url": "https://www.sec.gov/Archives/edgar/data/1046179/000162828026000020/tsm.htm",
                    "quote": "High Performance Computing segment comprised 52% of total revenue.",
                }],
            },
        }
        out["evidence"] = [
            {
                "form": "10-K",
                "accession": "0001045810-26-000010",
                "source_url": "https://www.sec.gov/Archives/edgar/data/1045810/000104581026000010/nvda.htm",
                "quote": "Compute and Networking revenue grew 150% year-over-year.",
            },
            {
                "form": "20-F",
                "accession": "0001628280-26-000020",
                "source_url": "https://www.sec.gov/Archives/edgar/data/1046179/000162828026000020/tsm.htm",
                "quote": "High Performance Computing segment comprised 52% of total revenue.",
            },
        ]
        out["evidence_gate"] = {"passed": True}
        out["accounting_gate"] = {"passed": True}
        out["valuation_gate"] = {"passed": True}
        out["asymmetry_gate"] = {"passed": True}
        return out

    monkeypatch.setattr(CompiledStateGraph, "invoke", mock_invoke)

    model = MultiCandidateArticleModel()
    req = ResearchRequest(
        query="Find best 2 tech stocks in AI right now",
        requested_ranking_count=2,
    )

    result = run_investigation(
        request=req,
        model=model,
        cases_root=tmp_path,
        generate_article=True,
        generate_video=False,
    )

    case_dir = tmp_path / result.case_id
    assert case_dir.exists()

    # 1. Verify memo.md exists and contains Executive Allocation synthesis
    memo_path = case_dir / "memo.md"
    assert memo_path.exists()
    memo_content = memo_path.read_text(encoding="utf-8")
    assert "## Executive Allocation & Research Synthesis" in memo_content
    assert "NVDA" in memo_content
    assert "55%" in memo_content
    assert "TSM" in memo_content
    assert "45%" in memo_content

    # 2. Verify investigation.json exists and records publishable status
    assert (case_dir / "investigation.json").exists()
    assert result.final_state["publication_readiness"]["status"] == "publishable"

    # 3. Verify article.md exists on disk and is returned in result
    article_path = case_dir / "article.md"
    assert article_path.exists()
    assert result.article_markdown is not None
    article_content = article_path.read_text(encoding="utf-8")
    assert "[1]" in article_content
    assert "[2]" in article_content
    assert "NVIDIA" in article_content
    assert "Taiwan Semiconductor" in article_content
    assert "## Primary Sources & Regulatory Receipts" in article_content

    # 4. Verify prompt passed to article writer included cohort and executive decision
    article_prompts = [p for p in model.captured_prompts if "Write an institutional" in p]
    assert len(article_prompts) == 1
    prompt_text = article_prompts[0]
    assert "$NVDA" in prompt_text
    assert "$TSM" in prompt_text
    assert "Executive Allocation" in prompt_text
    assert "55%" in prompt_text

    # 5. Strictly verify NO VIDEO or FACELESS artifacts were produced
    assert not (case_dir / "faceless").exists()
    assert not (case_dir / "faceless" / "dialogue.json").exists()
    assert not (case_dir / "faceless" / "video").exists()

    # 6. Verify run-manifest.json records article.md and omits faceless
    manifest_data = json.loads((case_dir / "run-manifest.json").read_text(encoding="utf-8"))
    assert "article.md" in manifest_data["artifacts"]
    assert "faceless/dialogue.json" not in manifest_data["artifacts"]
