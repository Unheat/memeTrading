"""Tests for grounded scout planning, Point-In-Time (PIT) dual-mode filtering, and candidate auto-registration."""
import json
from unittest.mock import MagicMock, patch
import pytest

from app.agent.contracts import ToolResultEnvelope
from app.agent.gate import evaluate_research_completeness
from app.agent.graph import create_research_graph, _has_evidence_gaps
from app.agent.planning import generate_research_plan, ResearchPlanSchema
from app.agent.screening import build_candidate_comparisons
from app.agent.state import ResearchRequest, create_initial_state
from app.agent.tool_result_ingestion import ingest_tool_results
from app.agent.tools import create_agent_tools
from app.articles.schemas import ArticleContent, ArticleRecord, ArticleSearchResult
from app.websearch.schemas import WebRecord, WebSearchResult


def test_dual_mode_pit_search_articles():
    """In backtest mode, block undated and future-dated articles. In normal flow, pass all."""
    mock_articles = [
        ArticleRecord(
            article_id="art_1",
            title="Old News",
            publisher="Reuters",
            url="https://example.com/1",
            published_utc="2025-05-01T10:00:00Z",
            summary="Old",
            domain="example.com",
            source="gdelt",
            access_status="ok",
        ),
        ArticleRecord(
            article_id="art_2",
            title="Future News",
            publisher="Bloomberg",
            url="https://example.com/2",
            published_utc="2025-07-01T10:00:00Z",
            summary="Future",
            domain="example.com",
            source="gdelt",
            access_status="ok",
        ),
        ArticleRecord(
            article_id="art_3",
            title="Undated News",
            publisher="CNBC",
            url="https://example.com/3",
            published_utc=None,
            summary="Undated",
            domain="example.com",
            source="gdelt",
            access_status="ok",
        ),
    ]
    mock_res = ArticleSearchResult(
        query="test",
        ticker="AI",
        days=7,
        records=tuple(mock_articles),
        source_summary={"gdelt": 3},
    )

    with patch("app.agent.tools._search_articles", return_value=mock_res):
        # 1. Backtest mode (cutoff: 2025-06-01)
        bt_tools = create_agent_tools(as_of_date="2025-06-01")
        search_tool_bt = next(t for t in bt_tools if t.name == "search_articles")
        bt_res = json.loads(search_tool_bt.invoke({"query": "AI"}))
        bt_urls = [a["url"] for a in bt_res["records"]]
        assert bt_urls == ["https://example.com/1"], "Backtest must exclude undated and future articles"

        # 2. Normal / Live mode (as_of_date=None)
        live_tools = create_agent_tools(as_of_date=None)
        search_tool_live = next(t for t in live_tools if t.name == "search_articles")
        live_res = json.loads(search_tool_live.invoke({"query": "AI"}))
        live_urls = [a["url"] for a in live_res["records"]]
        assert len(live_urls) == 3, "Live mode must not block any articles, even undated"


def test_dual_mode_pit_read_article():
    """In backtest mode, read_article blocks undated or future articles. In live mode, allows all."""
    future_art = ArticleContent(
        url="https://example.com/f",
        title="F",
        text="Content text here",
        author="Author",
        published_utc="2025-08-01T10:00:00Z",
        site_name="Example",
        status="ok",
        extraction_note=None,
    )
    undated_art = ArticleContent(
        url="https://example.com/u",
        title="U",
        text="Content text here",
        author="Author",
        published_utc=None,
        site_name="Example",
        status="ok",
        extraction_note=None,
    )
    valid_art = ArticleContent(
        url="https://example.com/v",
        title="V",
        text="Content text here",
        author="Author",
        published_utc="2025-04-01T10:00:00Z",
        site_name="Example",
        status="ok",
        extraction_note=None,
    )

    # Backtest mode
    bt_tools = create_agent_tools(as_of_date="2025-06-01")
    read_bt = next(t for t in bt_tools if t.name == "read_article")

    with patch("app.agent.tools._read_article", return_value=future_art):
        res = json.loads(read_bt.invoke({"url": "https://example.com/f"}))
        assert res["status"] == "unavailable"
        assert "look_ahead_blocked" in res["extraction_note"]

    with patch("app.agent.tools._read_article", return_value=undated_art):
        res = json.loads(read_bt.invoke({"url": "https://example.com/u"}))
        assert res["status"] == "unavailable"
        assert "undated_item_blocked_in_backtest" in res["extraction_note"]

    with patch("app.agent.tools._read_article", return_value=valid_art):
        res = json.loads(read_bt.invoke({"url": "https://example.com/v"}))
        assert res["status"] == "ok"

    # Live mode allows undated
    live_tools = create_agent_tools(as_of_date=None)
    read_live = next(t for t in live_tools if t.name == "read_article")
    with patch("app.agent.tools._read_article", return_value=undated_art):
        res = json.loads(read_live.invoke({"url": "https://example.com/u"}))
        assert res["status"] == "ok"


def test_planner_auto_seeds_candidate_workspaces():
    """Planner node automatically initializes candidates in state to avoid downstream entity_conflict."""
    class MockPlannerModel:
        def with_structured_output(self, schema):
            mock_runnable = MagicMock()
            mock_runnable.invoke.return_value = schema(
                brief="Analyze AI hardware leaders",
                research_type="multi_candidate_ranking",
                ranking_count=2,
                candidate_entities=["NVDA", "AVGO"],
                primary_questions=["Compare revenue growth", "Assess customer concentration"],
                requires_candidate_workspaces=True,
            )
            return mock_runnable

    req = ResearchRequest(query="Rank top 2 AI hardware chip makers", requested_ranking_count=2)
    state = create_initial_state(req, case_id="test_case")
    tools = create_agent_tools()
    graph = create_research_graph(MockPlannerModel(), tools)

    # Invoke just planner step
    plan_out = graph.nodes["planner"].invoke(state)
    assert "candidates" in plan_out
    assert "cand_nvda" in plan_out["candidates"]
    assert "cand_avgo" in plan_out["candidates"]
    assert plan_out["candidates"]["cand_nvda"]["ticker"] == "NVDA"
    assert plan_out["candidates"]["cand_avgo"]["ticker"] == "AVGO"


def test_tool_result_ingestion_auto_registers_candidate():
    """Ingesting tool results auto-registers candidate workspace when candidate_id is supplied on first write."""
    state = {
        "research_intent": {"requires_candidate_workspaces": True},
        "candidates": {},  # empty
        "evidence": [],
        "source_records": [],
        "searches_performed": [],
    }
    from langchain_core.messages import ToolMessage
    msg = ToolMessage(
        name="get_market_data",
        tool_call_id="call_1",
        content=json.dumps({
            "status": "ok",
            "candidate_id": "cand_tsm",
            "ticker": "TSM",
            "quote": {"price": 180.0},
        }),
    )
    update = ingest_tool_results(state, [msg])
    assert update["searches_performed"][-1]["status"] == "ok"
    assert "cand_tsm" in update["candidates"]
    assert update["candidates"]["cand_tsm"]["market_context"]["quote"]["price"] == 180.0


def test_foreign_issuer_status_recognized_in_envelope_and_reflection():
    """ok_foreign_issuer_unstructured is recognized as admissible evidence and does not loop reflection."""
    envelope = ToolResultEnvelope.from_payload({
        "status": "ok_foreign_issuer_unstructured",
        "ticker": "TSM",
        "candidate_id": "cand_tsm",
    })
    assert envelope.status == "ok_foreign_issuer_unstructured"

    # Candidate with market_context and ok_foreign_issuer_unstructured
    cand = {
        "candidate_id": "cand_tsm",
        "ticker": "TSM",
        "status": "discovered",
        "market_context": {"quote": {"price": 180.0}},
        "sec_financials": {"status": "ok_foreign_issuer_unstructured"},
        "diligence_dossier": {"verdict": "INVESTABLE"},
    }
    state = {
        "candidates": {"cand_tsm": cand},
        "work_queue": [],
        "source_records": [],
    }
    assert _has_evidence_gaps(state) is False, "Foreign issuer with foreign status must not be treated as a gap"


def test_screening_comparisons_unwraps_market_cap_dict():
    """build_candidate_comparisons safely extracts numeric float from fundamentals market_cap dict."""
    candidates = {
        "cand_nvda": {
            "candidate_id": "cand_nvda",
            "ticker": "NVDA",
            "market_context": {
                "fundamentals": {
                    "market_cap": {"value": 3000000000000.0, "reliable": True},
                },
                "quote": {"price": 120.0},
            },
        }
    }
    cards = build_candidate_comparisons(candidates, ["cand_nvda"], ["market_cap"])
    assert len(cards) == 1
    assert cards[0]["candidate_values"]["NVDA"]["value"] == 3000000000000.0
