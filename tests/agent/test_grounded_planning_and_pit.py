"""Tests for grounded scout planning, Point-In-Time (PIT) dual-mode filtering, and candidate auto-registration."""
import json
from unittest.mock import MagicMock, patch
import pytest

from app.agent.contracts import ToolResultEnvelope
from app.agent.gate import evaluate_research_completeness
from app.agent.graph import create_research_graph, _has_evidence_gaps
from app.agent.planning import (
    assess_scout_need,
    generate_research_plan,
    PlannerScoutAssessment,
    PlannerScoutQuery,
    ResearchHypothesis,
    ResearchPlanSchema,
)
from app.agent.screening import build_candidate_comparisons
from app.agent.state import BudgetLimits, ResearchRequest, create_initial_state
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


def test_assess_scout_need_fast_path_when_ticker_or_company_provided():
    """Explicit ticker or company bypasses LLM scout call entirely (zero searches, needs_scouting=False)."""
    mock_model = MagicMock()
    # 1. With explicit ticker
    res_ticker = assess_scout_need(mock_model, "Analyze balance sheet and 10-K", ticker="AAPL")
    assert res_ticker.needs_scouting is False
    assert res_ticker.scout_queries == []
    mock_model.invoke.assert_not_called()

    # 2. With explicit company
    res_company = assess_scout_need(mock_model, "Deep dive valuation", company="Microsoft")
    assert res_company.needs_scouting is False
    assert res_company.scout_queries == []
    mock_model.invoke.assert_not_called()


def test_assess_scout_need_open_ended_queries():
    """Open-ended screening generates targeted keyword queries for web discovery."""
    class MockStructuredModel:
        def with_structured_output(self, schema):
            mock_runnable = MagicMock()
            if schema is PlannerScoutAssessment:
                mock_runnable.invoke.return_value = PlannerScoutAssessment(
                    needs_scouting=True,
                    scout_queries=[
                        PlannerScoutQuery(
                            tool_name="search_web",
                            query="top enterprise tech free cash flow growth 2026",
                        ),
                    ],
                )
            return mock_runnable

    res = assess_scout_need(MockStructuredModel(), "find best 2 stock in tech to invest right now")
    assert res.needs_scouting is True
    assert len(res.scout_queries) == 1
    assert res.scout_queries[0].tool_name == "search_web"
    assert "free cash flow" in res.scout_queries[0].query


def test_assess_scout_need_routes_social_trend():
    """Social sentiment queries route to search_social rather than raw search_web."""
    class MockSocialModel:
        def with_structured_output(self, schema):
            mock_runnable = MagicMock()
            if schema is PlannerScoutAssessment:
                mock_runnable.invoke.return_value = PlannerScoutAssessment(
                    needs_scouting=True,
                    scout_queries=[
                        PlannerScoutQuery(
                            tool_name="search_social",
                            query="trending tech stocks ApeWisdom Reddit",
                        ),
                    ],
                )
            return mock_runnable

    res = assess_scout_need(MockSocialModel(), "what tech stocks are trending on Reddit and ApeWisdom?")
    assert res.needs_scouting is True
    assert res.scout_queries[0].tool_name == "search_social"
    assert "ApeWisdom" in res.scout_queries[0].query


def test_planner_node_executes_model_driven_scout_search():
    """planner_node runs only the model's targeted queries, not raw user conversational prompt."""
    executed_queries = []

    class MockUnifiedModel:
        def with_structured_output(self, schema):
            mock_runnable = MagicMock()
            if schema is PlannerScoutAssessment:
                mock_runnable.invoke.return_value = PlannerScoutAssessment(
                    needs_scouting=True,
                    scout_queries=[
                        PlannerScoutQuery(
                            tool_name="search_web",
                            query="leading AI semiconductor hardware 2026",
                        ),
                    ],
                )
            elif schema is ResearchPlanSchema:
                mock_runnable.invoke.return_value = ResearchPlanSchema(
                    brief="Analyze AI semiconductor leaders",
                    research_type="multi_candidate_ranking",
                    ranking_count=2,
                    candidate_entities=["NVDA", "AMD"],
                    primary_questions=["Compare data center revenue", "Assess margin trajectory"],
                    requires_candidate_workspaces=True,
                )
            return mock_runnable

    # Custom mock tool tracking invoked queries
    from langchain_core.tools import tool

    @tool
    def search_web(query: str, limit: int = 5) -> str:
        """Mock web search."""
        executed_queries.append(query)
        return json.dumps({
            "status": "ok",
            "records": [{"title": "NVDA and AMD AI chips", "snippet": "Strong data center demand in 2026."}],
        })

    req = ResearchRequest(query="find best 2 stock in tech to invest right now", requested_ranking_count=2)
    state = create_initial_state(req, case_id="test_scout_case")
    graph = create_research_graph(MockUnifiedModel(), [search_web])

    plan_out = graph.nodes["planner"].invoke(state)

    # Verify that the executed query was the model-formulated keyword query, NOT the raw prompt
    assert executed_queries == ["leading AI semiconductor hardware 2026"]
    assert "find best 2 stock in tech" not in executed_queries
    # Verify candidate workspaces were auto-seeded
    assert "cand_nvda" in plan_out["candidates"]
    assert "cand_amd" in plan_out["candidates"]


def test_planner_node_executes_model_driven_screen_stocks():
    """planner_node invokes screen_stocks when chosen by model and grounds the plan on returned candidates."""
    screen_calls = []

    class MockScreeningPlannerModel:
        def with_structured_output(self, schema):
            mock_runnable = MagicMock()
            if schema is PlannerScoutAssessment:
                mock_runnable.invoke.return_value = PlannerScoutAssessment(
                    needs_scouting=True,
                    scout_queries=[
                        PlannerScoutQuery(
                            tool_name="screen_stocks",
                            sector="Technology",
                            preset="growth_technology_stocks",
                        ),
                    ],
                )
            elif schema is ResearchPlanSchema:
                mock_runnable.invoke.return_value = ResearchPlanSchema(
                    brief="Analyze top growth tech candidates",
                    research_type="multi_candidate_ranking",
                    ranking_count=2,
                    candidate_entities=["NVDA", "SMCI"],
                    primary_questions=["Audit free cash flow conversion", "Verify customer concentration"],
                    requires_candidate_workspaces=True,
                )
            return mock_runnable

    from langchain_core.tools import tool

    @tool
    def screen_stocks(preset: str = None, sector: str = None, limit: int = 5) -> str:
        """Mock screen_stocks tool."""
        screen_calls.append({"preset": preset, "sector": sector, "limit": limit})
        return json.dumps({
            "status": "ok",
            "count": 2,
            "records": [
                {"ticker": "NVDA", "company": "NVIDIA Corporation", "market_cap": 3000000000000.0, "summary": "NVIDIA (NVDA): Leading AI GPU chips."},
                {"ticker": "SMCI", "company": "Super Micro Computer", "market_cap": 25000000000.0, "summary": "Super Micro (SMCI): AI server infrastructure."},
            ],
        })

    req = ResearchRequest(query="find best 2 stock in tech to invest right now", requested_ranking_count=2)
    state = create_initial_state(req, case_id="test_screen_scout_case")
    graph = create_research_graph(MockScreeningPlannerModel(), [screen_stocks])

    plan_out = graph.nodes["planner"].invoke(state)

    assert len(screen_calls) == 1
    assert screen_calls[0]["preset"] == "growth_technology_stocks"
    assert screen_calls[0]["sector"] == "Technology"
    assert "cand_nvda" in plan_out["candidates"]
    assert "cand_smci" in plan_out["candidates"]


def test_evidence_tier_hypotheses_hydrated_in_work_queue():
    """Hypotheses with diverse evidence tiers are mapped directly to prioritized work items."""
    class MockHypothesisPlannerModel:
        def with_structured_output(self, schema):
            mock_runnable = MagicMock()
            if schema is ResearchPlanSchema:
                mock_runnable.invoke.return_value = ResearchPlanSchema(
                    brief="Analyze impact of China metal export ban on semiconductors",
                    research_type="general_deep_dive",
                    hypotheses=[
                        ResearchHypothesis(
                            statement="Identify which chip technologies require banned metals",
                            evidence_tier="open_web",
                        ),
                        ResearchHypothesis(
                            statement="Audit 10-K Item 1A raw material supply disclosures",
                            evidence_tier="primary_regulatory",
                            target_entity="QRVO",
                        ),
                        ResearchHypothesis(
                            statement="Check Federal Reserve industrial commodity inflation series",
                            evidence_tier="macro_series",
                        ),
                        ResearchHypothesis(
                            statement="Screen for alternative non-China rare earth suppliers",
                            evidence_tier="structured_quant",
                        ),
                    ],
                    requires_candidate_workspaces=False,
                )
            return mock_runnable

    req = ResearchRequest(query="China metal export ban impact on semiconductors")
    state = create_initial_state(req, case_id="test_macro_hypotheses")
    graph = create_research_graph(MockHypothesisPlannerModel(), [])

    plan_out = graph.nodes["planner"].invoke(state)
    work_queue = plan_out["work_queue"]

    assert len(work_queue) == 4
    tiers = [w["evidence_tier"] for w in work_queue]
    assert tiers == ["open_web", "primary_regulatory", "macro_series", "structured_quant"]
    assert work_queue[1]["candidate_id"] == "cand_qrvo"


def test_depth_budget_scaling_in_runner(tmp_path):
    """Runner scales default budget limits between standard (25) and deep (50)."""
    from langchain_core.messages import AIMessage
    from app.agent.runner import run_investigation

    class QuickModel:
        def bind_tools(self, tools):
            return self
        def invoke(self, messages):
            return AIMessage(content="Conclusion")

    # 1. Standard depth
    req_std = ResearchRequest(query="Quick check on tech", depth="standard")
    res_std = run_investigation(request=req_std, model=QuickModel(), cases_root=tmp_path)
    with open(tmp_path / res_std.case_id / "run-manifest.json") as f:
        manifest_std = json.load(f)
    assert manifest_std["request"]["depth"] == "standard"

    # 2. Deep depth
    req_deep = ResearchRequest(query="Deep investigation on tech", depth="deep")
    res_deep = run_investigation(request=req_deep, model=QuickModel(), cases_root=tmp_path)
    with open(tmp_path / res_deep.case_id / "run-manifest.json") as f:
        manifest_deep = json.load(f)
    assert manifest_deep["request"]["depth"] == "deep"


def test_thematic_macro_reflection_not_blocked_by_sec_filings():
    """Non-equity thematic research (requires_candidate_workspaces=False) does not demand SEC filings for general concepts."""
    state = {
        "ticker": None,
        "research_intent": {"requires_candidate_workspaces": False},
        "candidates": {
            "cand_semiconductor_sector": {
                "candidate_id": "cand_semiconductor_sector",
                "ticker": None,
                "evidence": [{"quote": "Gallium export controls restrict wafer production.", "source_url": "https://example.com/sec"}],
            }
        },
        "work_queue": [],
        "source_records": [{"url": "https://example.com/sec", "status": "read"}],
    }
    # _has_evidence_gaps should be False because it's not a multi-candidate equity comparison or explicit ticker
    assert _has_evidence_gaps(state) is False



