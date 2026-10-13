"""Tests for Investment Committee and Executive Memo synchronization."""
from unittest.mock import MagicMock
import pytest
from app.agent.committee import ICVerdict, run_investment_committee
from app.agent.gate import evaluate_asymmetry_gate
from app.agent.memo import render_research_report
from app.agent.state import create_initial_state, ResearchRequest


def test_committee_returns_synchronized_asymmetry_gate():
    """Verify run_investment_committee returns a synchronized asymmetry_gate."""
    mock_model = MagicMock()
    mock_response = MagicMock()
    mock_response.content = """{
        "committee_verdict": "APPROVED_LONG",
        "conviction_tier": "HIGH CONVICTION 🔥🔥🔥",
        "cio_deliberation_summary": "Scuttlebutt confirms DDR5 server tightness with 5.21:1 reward-to-risk.",
        "passing_rationale": "High channel acceleration with dynamic downside floor."
    }"""
    mock_model.invoke.return_value = mock_response

    state = {
        "ticker": "MU",
        "current_price": 405.12,
        "market_context": {
            "quote": {"price": 405.12, "volume": 20_000_000},
            "addv_20d": {"value": 50_000_000.0},
            "atr_14": 25.0,
            "fundamentals": {"market_cap": {"value": 450_000_000_000}},
        },
        "quant_report": {
            "status": "available",
            "valuation": {
                "fair_value_range": {
                    "low": 164.35,
                    "base": 433.78,
                    "high": 731.37,
                },
            },
        },
        "channel_check_report": {
            "status": "available",
            "channel_verdict": "CHANNEL_ACCELERATION",
        },
        "expectation_gap": {
            "arbitrage_verdict": "UNPRICED_CHANNEL_ACCELERATION",
        },
        "confidence": 0.85,
    }

    res = run_investment_committee(state, mock_model)
    assert "ic_verdict" in res
    assert "asymmetry_gate" in res

    ic = res["ic_verdict"]
    gate = res["asymmetry_gate"]

    assert ic.verdict == "APPROVED_LONG"
    assert ic.reward_to_risk_ratio == pytest.approx(5.22, abs=0.05)
    assert ic.kelly_position_size_pct > 0.0

    assert gate["passed"] is True
    assert gate["reward_to_risk_ratio"] == pytest.approx(5.22, abs=0.05)
    assert gate["upside_anchor"] == 731.37
    assert gate["scuttlebutt_acceleration"] is True

    # Test that evaluate_asymmetry_gate directly recognizes the committee verdict
    evaluated_gate = evaluate_asymmetry_gate({"ic_verdict": ic})
    assert evaluated_gate["passed"] is True
    assert evaluated_gate["reward_to_risk_ratio"] == pytest.approx(5.22, abs=0.05)


def test_render_research_report_leads_with_committee_verdict():
    """Verify render_research_report leads with the Investment Committee allocation table and CIO summary."""
    ic = ICVerdict(
        ticker="MU",
        verdict="APPROVED_LONG",
        conviction_tier="HIGH CONVICTION 🔥🔥🔥",
        reward_to_risk_ratio=5.21,
        kelly_position_size_pct=0.05,
        passing_discipline_checks={"liquidity_gate": "PASS", "asymmetry_gate": "PASS"},
        cio_deliberation_summary="Ground-truth scuttlebutt validates wafer crowd-out; allocate 5.0% under Kelly.",
        upside_anchor=731.37,
        upside_anchor_source="quant_high_channel_acceleration",
        bear_anchor_source="channel_acceleration_dynamic_floor",
        bear_floor=342.54,
    )

    state = create_initial_state(ResearchRequest(query="Audit DDR5 and HBM3E"), case_id="test_sync_memo")
    state["ticker"] = "MU"
    state["company"] = "Micron Technology"
    state["ic_verdict"] = ic

    pre_committee_chat = "Preliminary DCF shows modest 7.1% upside to base case fair value of $433.78."

    report = render_research_report(state, final_text=pre_committee_chat)

    # 1. Executive allocation section must be present and lead with the committee's decision
    assert "## Executive Allocation & Research Synthesis" in report
    assert "### Investment Committee Deliberation ($MU)" in report
    assert "**APPROVED_LONG**" in report
    assert "**HIGH CONVICTION 🔥🔥🔥**" in report
    assert "**5.21x**" in report
    assert "**5.0%**" in report
    assert "$731.37" in report
    assert "$342.54" in report
    assert "Ground-truth scuttlebutt validates wafer crowd-out; allocate 5.0% under Kelly." in report

    # 2. Preliminary text is subordinated under field telemetry, not masquerading as the top verdict
    assert "### Grounded Research Synthesis & Field Telemetry" in report
    assert "Preliminary DCF shows modest 7.1% upside" in report
