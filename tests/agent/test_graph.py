"""Tests for LangGraph state graph execution using ScriptedModel."""
import json

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool

from app.agent import graph as graph_module
from app.agent.graph import create_research_graph
from app.agent.state import ResearchRequest, create_initial_state


class ScriptedModel:
    """Deterministic offline model for graph workflow testing."""

    def __init__(self):
        """Initialize model invocation count."""
        self.call_count = 0

    def bind_tools(self, tools):
        """Return this deterministic model after accepting graph tools."""
        return self

    def invoke(self, messages):
        """Return the next scripted response for the three-stage workflow."""
        self.call_count += 1
        if self.call_count == 1:
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "fake_search",
                        "args": {"query": "XYZ partnership"},
                        "id": "call_1",
                        "type": "tool_call",
                    }
                ],
            )
        prompt = str(getattr(messages[-1], "content", ""))
        if "Construct the institutional Bull Case" in prompt:
            return AIMessage(content='{"catalysts": ["Demand"], "operating_leverage_drivers": ["Margin"], "bull_target_price": null, "bull_thesis_summary": "Source-bound bull case."}')
        if "hostile short-seller red team" in prompt:
            return AIMessage(content="""{
  "falsifiable_objections": ["Objection 1", "Objection 2"],
  "numeric_kill_criteria": ["Kill Trigger 1: Gross margin drop", "Kill Trigger 2: DSI increase"],
  "bear_floor_price": 75.0,
  "bear_thesis_summary": "Cyclical trap."
}""")
        if "Review the investment case" in prompt:
            return AIMessage(content="CIO deliberation: HIGH CONVICTION.")
        if self.call_count == 2:
            return AIMessage(content="Forensic synthesis: XYZ partnership claim is contradicted by 8-K.")
        return AIMessage(content="Cited thematic thesis.")


@tool
def fake_search(query: str) -> str:
    """Return a deterministic fake search result."""
    return '{"status": "ok", "result": "found 8-K showing non-binding LOI"}'


@tool
def get_market_data(ticker: str) -> str:
    """Return deterministic gate-complete market context for graph ingestion tests."""
    return json.dumps(
        {
            "status": "ok",
            "ticker": ticker,
            "quote": {"value": 101.5},
            "fundamentals": {"shares_outstanding": 10_000_000.0},
            "currency": "USD",
            "as_of": "2026-09-15T00:00:00Z",
            "addv_20d": {"value": 50_000_000.0},
        }
    )


@tool
def get_company_research(ticker: str) -> str:
    """Return deterministic consensus context for graph ingestion tests."""
    return json.dumps({"status": "ok", "ticker": ticker, "ratings": {"buy": 4}})


def _add_sufficient_mocked_evidence(state):
    """Seed deterministic evidence required to enter red-team and committee stages."""
    ticker = state.get("ticker") or "XYZ"
    cid = f"cand_{ticker.lower()}"
    mkt = {
        "quote": {"value": 100.0},
        "fundamentals": {"shares_outstanding": 10_000_000.0},
        "currency": "USD",
        "as_of": "2026-09-15T00:00:00Z",
        "addv_20d": {"value": 50_000_000.0},
    }
    sec = {
        "status": "ok", "periods": ["2026-Q2"],
        "cash_from_operations": {"2026-Q2": 2_000_000_000.0},
        "capex": {"2026-Q2": 500_000_000.0},
        "cash_and_equivalents": {"2026-Q2": 8_000_000_000.0},
        "total_debt": {"2026-Q2": 5_000_000_000.0},
        "gross_margin_pct": {"2026-Q2": 0.32},
    }
    state.update(
        {
            "company": "XYZ Corporation",
            "cik": "0000123456",
            "market_context": mkt,
            "sec_corpora": [{"corpus_id": "XYZ-2026-09-15-001"}],
            "sec_financials": sec,
            "searches_performed": [
                {"tool": "get_market_data", "status": "ok", "tool_call_id": "mkt-init"},
                {"tool": "pull_sec_filings", "status": "ok", "tool_call_id": "sec-init"},
            ],
            "candidates": {
                cid: {
                    "candidate_id": cid,
                    "ticker": ticker,
                    "company": "XYZ Corporation",
                    "cik": "0000123456",
                    "market_context": mkt,
                    "sec_financials": sec,
                    "diligence_dossier": {
                        "status": "ok",
                        "ticker": ticker,
                        "candidate_id": cid,
                        "company": "XYZ Corporation",
                        "valuation": {
                            "fair_value": 150.0,
                            "implied_growth_rate": 0.08,
                            "reward_to_risk_ratio": 3.2,
                            "reproducibility": "pass",
                        },
                        "bull_catalysts": ["Demand expansion"],
                        "bull_thesis": "Source-bound bull case.",
                        "bear_kill_triggers": ["Kill Trigger 1: Gross margin drop", "Kill Trigger 2: DSI increase"],
                        "bear_thesis": "Cyclical trap.",
                        "bear_floor": 75.0,
                        "forensic_verdict": "QUALIFIED_NORMALIZED_ADJUSTMENT",
                        "moat_rating": "WIDE",
                    },
                }
            },
        }
    )


def test_agent_graph_stops_before_red_team_when_evidence_is_insufficient():
    """Prove old ungated graph path now terminates before decision stages."""
    model = ScriptedModel()
    graph = create_research_graph(model=model, tools=[fake_search])

    req = ResearchRequest(query="Give an investment recommendation for XYZ", ticker="XYZ")
    final_state = graph.invoke(create_initial_state(req, case_id="case_test"))

    assert final_state["tool_calls"] == 1
    assert final_state["status"] == "insufficient_evidence"
    assert final_state["thesis_breakers"] == []
    assert final_state["ic_verdict"] is None
    assert "SEC CIK identity is missing" in final_state["evidence_gate"]["missing_evidence"]


def test_agent_graph_execution_loop():
    """Prove graph fixture path reaches red team and committee with sufficient evidence."""
    model = ScriptedModel()
    graph = create_research_graph(model=model, tools=[fake_search])

    req = ResearchRequest(query="Give an investment recommendation for XYZ", ticker="XYZ")
    initial_state = create_initial_state(req, case_id="case_test")
    _add_sufficient_mocked_evidence(initial_state)

    final_state = graph.invoke(initial_state)

    assert final_state["tool_calls"] == 1
    assert len(final_state["messages"]) >= 3
    assert "thesis_breakers" in final_state
    assert len(final_state["thesis_breakers"]) >= 2
    assert "Kill Trigger 1" in final_state["thesis_breakers"][0]
    assert "ic_verdict" in final_state
    assert final_state["ic_verdict"].ticker == "XYZ"


def test_market_and_parallel_tool_results_are_ingested_before_committee(monkeypatch):
    """Prove parallel tool results merge and market context reaches committee state."""
    observed_committee_state = {}

    class ParallelToolModel:
        """Request two tools in parallel, then finish investigation."""

        def __init__(self):
            """Initialize model invocation count."""
            self.call_count = 0

        def bind_tools(self, tools):
            """Return this deterministic model after accepting graph tools."""
            return self

        def invoke(self, messages):
            """Request parallel context tools once, then return synthesis text."""
            self.call_count += 1
            if self.call_count == 1:
                return AIMessage(
                    content="",
                    tool_calls=[
                        {"name": "get_market_data", "args": {"ticker": "XYZ"}, "id": "market-1", "type": "tool_call"},
                        {"name": "get_company_research", "args": {"ticker": "XYZ"}, "id": "research-1", "type": "tool_call"},
                    ],
                )
            return AIMessage(content="Investigation complete.")

    def fake_committee(state, model):
        """Capture committee input state and return a marker verdict."""
        observed_committee_state.update(state)
        return {"ic_verdict": "passed"}

    monkeypatch.setattr(graph_module, "run_investment_committee", fake_committee)
    graph = create_research_graph(
        model=ParallelToolModel(), tools=[get_market_data, get_company_research]
    )
    initial_state = create_initial_state(
        ResearchRequest(query="Give an investment recommendation for XYZ", ticker="XYZ"), case_id="parallel"
    )
    _add_sufficient_mocked_evidence(initial_state)

    final_state = graph.invoke(initial_state)

    assert observed_committee_state["market_context"]["quote"]["value"] == 101.5
    assert observed_committee_state["consensus_snapshot"]["ratings"] == {"buy": 4}
    assert [receipt["tool_call_id"] for receipt in final_state["searches_performed"] if receipt.get("tool_call_id") in {"market-1", "research-1"}] == [
        "market-1",
        "research-1",
    ]


def test_agent_graph_executes_exact_remaining_tool_budget(monkeypatch):
    """Prove excess parallel calls are clipped while allowed call pairs stay complete."""
    executed_queries = []

    @tool
    def budgeted_search(query: str) -> str:
        """Record each allowed execution and return a JSON result."""
        executed_queries.append(query)
        return json.dumps({"status": "ok", "query": query})

    class ExcessToolModel:
        """Return more parallel calls than remaining budget allows."""

        def __init__(self):
            """Initialize model invocation count."""
            self.call_count = 0

        def bind_tools(self, tools):
            """Return this deterministic model after accepting graph tools."""
            return self

        def invoke(self, messages):
            """Offer three tool calls on first invocation, then finish."""
            self.call_count += 1
            if self.call_count == 1:
                return AIMessage(
                    content="",
                    tool_calls=[
                        {"name": "budgeted_search", "args": {"query": query}, "id": f"call-{index}", "type": "tool_call"}
                        for index, query in enumerate(("one", "two", "three"), start=1)
                    ],
                )
            return AIMessage(content="Investigation complete.")

    monkeypatch.setattr(
        graph_module,
        "run_investment_committee",
        lambda state, model: {"ic_verdict": "passed"},
    )
    graph = create_research_graph(model=ExcessToolModel(), tools=[budgeted_search])
    initial_state = create_initial_state(
        ResearchRequest(query="Investigate budget", ticker="XYZ"), case_id="budget"
    )
    initial_state["budget_state"]["max_tool_calls"] = 2

    final_state = graph.invoke(initial_state)

    assert final_state["tool_calls"] == 2
    assert executed_queries == ["one", "two"]
    ai_tool_calls = [
        call
        for message in final_state["messages"]
        if isinstance(message, AIMessage)
        for call in message.tool_calls
    ]
    tool_messages = [
        message for message in final_state["messages"] if isinstance(message, ToolMessage)
    ]
    assert [call["id"] for call in ai_tool_calls] == ["call-1", "call-2"]
    assert [message.tool_call_id for message in tool_messages] == ["call-1", "call-2"]


def test_candidate_diligence_dossier_promoted_without_redundant_execution(monkeypatch):
    """Prove completed candidate diligence dossier is promoted and skips duplicate engine runs in Stage 5."""
    class DirectFinishModel:
        def __init__(self):
            self.call_count = 0

        def bind_tools(self, tools):
            return self

        def invoke(self, messages):
            self.call_count += 1
            return AIMessage(content="Research finished.")

    assert not hasattr(graph_module, "run_quant_analysis")
    assert not hasattr(graph_module, "run_bull_advocate")
    assert not hasattr(graph_module, "run_adversarial_red_team")

    observed_committee_state = {}

    def mock_committee(state, model):
        observed_committee_state.update(state)
        return {"ic_verdict": "approved"}

    monkeypatch.setattr(graph_module, "run_investment_committee", mock_committee)

    graph = create_research_graph(model=DirectFinishModel(), tools=[])
    req = ResearchRequest(query="Rank candidates", ticker=None)
    state = create_initial_state(req, case_id="dossier_promo")
    _add_sufficient_mocked_evidence(state)

    state["candidates"] = {
        "cand_msft": {
            "candidate_id": "cand_msft",
            "ticker": "MSFT",
            "company": "Microsoft Corp",
            "cik": "0000789019",
            "market_context": state["market_context"],
            "sec_financials": state["sec_financials"],
            "diligence_dossier": {
                "status": "ok",
                "ticker": "MSFT",
                "candidate_id": "cand_msft",
                "company": "Microsoft Corp",
                "valuation": {
                    "fair_value": 450.0,
                    "implied_growth_rate": 0.12,
                    "reward_to_risk_ratio": 3.5,
                    "reproducibility": "pass",
                },
                "bull_catalysts": ["Azure AI acceleration", "Copilot adoption"],
                "bull_thesis": "Strong cloud operating leverage.",
                "bear_kill_triggers": ["Azure growth below 20%", "CapEx exceeding $80B"],
                "bear_thesis": "AI CapEx overspend.",
                "bear_floor": 320.0,
                "forensic_verdict": "QUALIFIED_NORMALIZED_ADJUSTMENT",
                "moat_rating": "WIDE",
            },
        }
    }

    final_state = graph.invoke(state)

    assert final_state["ticker"] == "MSFT"
    assert final_state["company"] == "Microsoft Corp"
    assert final_state["accounting_gate"]["passed"] is True
    assert final_state["valuation_gate"]["passed"] is True
    assert final_state["asymmetry_gate"]["passed"] is True
    assert final_state["ic_verdict"] == "approved"
    assert "Azure growth below 20%" in final_state["thesis_breakers"]
    assert observed_committee_state["bull_report"].ticker == "MSFT"
    assert observed_committee_state["adversarial_report"].bear_floor_price == 320.0


def test_evidence_gaps_identifies_missing_candidate_diligence():
    """Prove supervisor reflection catches candidates lacking diligence or valuation."""
    from app.agent.graph import _has_evidence_gaps

    state = {
        "candidates": {
            "cand_nvda": {
                "candidate_id": "cand_nvda",
                "ticker": "NVDA",
                "market_context": {"quote": {"value": 120.0}},
                "sec_financials": {"status": "ok", "periods": ["2026-Q2"]},
            }
        },
        "source_records": [],
        "work_queue": [],
    }
    # Missing diligence/valuation -> gap exists
    assert _has_evidence_gaps(state) is True

    # Once diligence dossier is present -> no gap
    state["candidates"]["cand_nvda"]["diligence_dossier"] = {"status": "ok", "valuation": {"fair_value": 140.0}}
    assert _has_evidence_gaps(state) is False

    # Alternatively, valuation alone satisfies requirement
    del state["candidates"]["cand_nvda"]["diligence_dossier"]
    state["candidates"]["cand_nvda"]["valuation"] = {"fair_value": 140.0}
    assert _has_evidence_gaps(state) is False


def test_evidence_gaps_respects_early_veto_fast_path():
    """Prove supervisor reflection honors fast-path early veto without forcing further tool calls."""
    from app.agent.graph import _has_evidence_gaps

    state = {
        "candidates": {
            "cand_toxic": {
                "candidate_id": "cand_toxic",
                "ticker": "TOXIC",
                "status": "vetoed",
                "veto_reason": "Auditor resignation under Item 4.01 8-K; internal control material weakness.",
            }
        },
        "source_records": [],
        "work_queue": [],
    }
    # Vetoed candidate does not block research completion
    assert _has_evidence_gaps(state) is False


def test_single_candidate_does_not_require_comparisons():
    """Prove single candidate diligence does not trigger a missing comparison matrix gap."""
    from app.agent.graph import _has_evidence_gaps

    state = {
        "candidates": {
            "cand_msft": {
                "candidate_id": "cand_msft",
                "ticker": "MSFT",
                "market_context": {"quote": {"value": 450.0}},
                "sec_financials": {"status": "ok", "periods": ["2026-Q2"]},
                "valuation": {"fair_value": 480.0},
            }
        },
        "comparisons": [],
        "source_records": [],
        "work_queue": [],
    }
    assert _has_evidence_gaps(state) is False

    # But two active candidates do require a comparison matrix
    state["candidates"]["cand_aapl"] = {
        "candidate_id": "cand_aapl",
        "ticker": "AAPL",
        "market_context": {"quote": {"value": 230.0}},
        "sec_financials": {"status": "ok", "periods": ["2026-Q2"]},
        "valuation": {"fair_value": 240.0},
    }
    assert _has_evidence_gaps(state) is True


def test_register_candidate_tool_supports_veto_status_and_reason():
    """Prove register_candidate tool and ingestion persist early vetoes in candidate workspace."""
    from app.agent.tools import create_agent_tools
    from app.agent.tool_result_ingestion import ingest_tool_results

    tools = {t.name: t for t in create_agent_tools()}
    reg_tool = tools["register_candidate"]

    raw_result = reg_tool.invoke({
        "ticker": "SMCI",
        "company": "Super Micro Computer",
        "status": "vetoed",
        "reason": "Auditor resigned and special committee investigation active.",
    })
    payload = json.loads(raw_result)
    assert payload["status"] == "ok"
    assert payload["candidate_status"] == "vetoed"
    assert "Auditor resigned" in payload["reason"]

    tool_msg = ToolMessage(content=raw_result, name="register_candidate", tool_call_id="call-veto-1")
    state = {"candidates": {}, "research_intent": {"requires_candidate_workspaces": True}}
    updates = ingest_tool_results(state, [tool_msg])

    assert "cand_smci" in updates["candidates"]
    cand = updates["candidates"]["cand_smci"]
    assert cand["status"] == "vetoed"
    assert "Auditor resigned" in cand["veto_reason"]


