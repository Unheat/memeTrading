"""Tests for deterministic research evidence gating."""
from app.agent.gate import evaluate_research_completeness
from app.agent.memo import render_forensic_memo
from app.agent.state import ResearchRequest, create_initial_state


def test_gate_returns_no_position_when_required_evidence_is_missing():
    """Block decision stages when identity, market, or SEC evidence is absent."""
    state = create_initial_state(ResearchRequest(query="Give an investment recommendation for MU", ticker="MU", company="Micron"), "MU-2026-09-01-001")

    outcome = evaluate_research_completeness(state)

    assert outcome["passed"] is False
    assert outcome["status"] == "insufficient_evidence"
    assert outcome["decision"] == "NO_POSITION"
    assert outcome["allocation_pct"] == 0.0
    assert "SEC CIK identity is missing" in outcome["missing_evidence"]


def test_insufficient_evidence_memo_excludes_raw_model_claims_and_targets():
    """Render only deterministic evidence gaps for no-position research."""
    state = create_initial_state(ResearchRequest(query="Give an investment recommendation for MU", ticker="MU", company="Micron"), "MU-2026-09-01-001")
    state["status"] = "insufficient_evidence"
    state["evidence_gate"] = evaluate_research_completeness(state)

    memo = render_forensic_memo(state, "BUY MU with $999 target and 12-month horizon.")

    assert "NO_POSITION" in memo
    assert "BUY MU" not in memo
    assert "$999" not in memo
    assert "required next evidence" in memo.lower()
