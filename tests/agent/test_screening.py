"""Tests for candidate isolation and evidence-backed ranking completion."""
from __future__ import annotations

import json

from langchain_core.messages import ToolMessage

from app.agent.gate import evaluate_research_completeness
from app.agent.screening import CandidateResearchState
from app.agent.state import ResearchRequest, create_initial_state
from app.agent.tool_result_ingestion import ingest_tool_results


def test_candidate_research_state_round_trip() -> None:
    """Verify a candidate workspace serializes without losing identity."""
    candidate = CandidateResearchState(candidate_id="cand_msft", ticker="MSFT", company="Microsoft", cik="789019", market_context={"quote": {"price": 450.0}})
    restored = CandidateResearchState.from_dict(candidate.to_dict())
    assert restored.ticker == "MSFT"
    assert restored.cik == "789019"


def test_candidate_payload_stays_out_of_global_state() -> None:
    """Candidate-tagged financial results cannot populate single-company fields."""
    state = create_initial_state(ResearchRequest(query="Rank the best 2 tech stocks"), "isolation-1")
    messages = [
        ToolMessage(name="register_candidate", tool_call_id="register", content=json.dumps({"status": "ok", "candidate_id": "cand_msft", "ticker": "MSFT", "company": "Microsoft"})),
        ToolMessage(name="get_market_data", tool_call_id="market", content=json.dumps({"status": "ok", "candidate_id": "cand_msft", "ticker": "MSFT", "quote": {"price": 450}})),
        ToolMessage(name="get_sec_financials", tool_call_id="sec", content=json.dumps({"status": "ok", "candidate_id": "cand_msft", "ticker": "MSFT", "periods": ["2026-Q2"]})),
    ]
    update = ingest_tool_results(state, messages)
    assert update["candidates"]["cand_msft"]["market_context"]["quote"]["price"] == 450
    assert update["candidates"]["cand_msft"]["sec_financials"]["periods"] == ["2026-Q2"]
    assert "market_context" not in update
    assert "sec_financials" not in update


def test_unregistered_or_mismatched_candidate_is_quarantined() -> None:
    """Reject unsafe candidate payloads instead of allowing global fallback writes."""
    state = create_initial_state(ResearchRequest(query="Rank the best 2 tech stocks"), "isolation-2")
    state["candidates"]["cand_msft"] = {"candidate_id": "cand_msft", "ticker": "MSFT", "company": "Microsoft", "sec_corpora": [], "evidence": []}
    update = ingest_tool_results(state, [ToolMessage(name="get_market_data", tool_call_id="bad", content=json.dumps({"status": "ok", "candidate_id": "cand_msft", "ticker": "NVDA", "quote": {"price": 1}}))])
    receipt = update["searches_performed"][-1]
    assert receipt["status"] == "error"
    assert "ticker mismatch" in receipt["error"]
    assert "market_context" not in update


def test_ranking_requires_requested_count_and_comparison() -> None:
    """Return incomplete rather than fabricate a candidate ranking."""
    state = create_initial_state(ResearchRequest(query="Rank the best 3 tech companies"), "ranking-1")
    state["candidates"] = {
        "cand_msft": {"ticker": "MSFT", "market_context": {"quote": {"price": 1}}, "sec_financials": {"periods": ["Q"]}},
        "cand_nvda": {"ticker": "NVDA", "market_context": {"quote": {"price": 1}}, "sec_financials": {"periods": ["Q"]}},
    }
    outcome = evaluate_research_completeness(state)
    assert outcome["status"] == "research_incomplete"
    assert outcome["requested_ranking_count"] == 3
    assert outcome["allocation_pct"] == 0.0
    assert "Requested 3 evidence-backed candidates; collected 2." in outcome["missing_evidence"]
