"""Tests for the investment committee deliberation and sizing node."""
from unittest.mock import MagicMock
import pytest
from langchain_core.messages import AIMessage
from app.agent.state import ResearchRequest, create_initial_state
from app.agent.adversarial import AdversarialReport
from app.agent.committee import run_investment_committee, ICVerdict


class FakeCIOModel:
    """Mock CIO model generating committee deliberation text."""

    def invoke(self, messages):
        return AIMessage(
            content="""### Investment Committee Deliberation
Target: $MU | Conviction: HIGH CONVICTION 🔥🔥🔥
The 3:1 Asymmetry hurdle is satisfied. Grassroots DDR5 demand is verified by gross margin expansion in the 10-Q.
Allocation: 8.0% Quarter-Kelly position size."""
        )


def test_investment_committee_approves_when_asymmetry_and_gates_pass():
    req = ResearchRequest(query="Investigate MU", ticker="MU", company="Micron")
    state = create_initial_state(req, case_id="case_mu_ic")
    state["market_context"] = {
        "quote": {"price": 100.0},
        "addv_20d": {"value": 50_000_000.0},
        "cap_tier": "large",
    }
    state["consensus_snapshot"] = {
        "price_targets": {"mean": {"value": 145.0}},  # +45% upside
        "earnings_proximity_flag": "SAFE",
    }
    state["adversarial_report"] = AdversarialReport(
        ticker="MU",
        falsifiable_objections=("Objection 1", "Objection 2"),
        numeric_kill_criteria=("Kill 1", "Kill 2"),
        bear_floor_price=85.0,  # 15% downside -> 45/15 = 3.0 ratio!
        bear_thesis_summary="Capex risk.",
    )
    state["confidence"] = 0.85

    model = FakeCIOModel()
    updates = run_investment_committee(state, model=model)

    assert "ic_verdict" in updates
    verdict = updates["ic_verdict"]
    assert isinstance(verdict, ICVerdict)
    assert verdict.ticker == "MU"
    assert "APPROVED_LONG" in verdict.verdict
    assert verdict.reward_to_risk_ratio == pytest.approx(3.0)
    assert verdict.kelly_position_size_pct == pytest.approx(0.08)
    assert "HIGH CONVICTION" in verdict.conviction_tier


def test_investment_committee_passes_when_illiquid_or_blackout():
    req = ResearchRequest(query="Investigate SKETCHY", ticker="SKETCHY")
    state = create_initial_state(req, case_id="case_sketchy")
    state["market_context"] = {
        "quote": {"price": 5.0},
        "addv_20d": {"value": 100_000.0},  # $100k << $5M limit!
        "cap_tier": "micro",
    }
    state["consensus_snapshot"] = {
        "earnings_proximity_flag": "BLACKOUT_RISK",
    }

    model = FakeCIOModel()
    updates = run_investment_committee(state, model=model)

    verdict = updates["ic_verdict"]
    assert "PASSED" in verdict.verdict
    assert verdict.kelly_position_size_pct == 0.0
    assert "PASSED" in verdict.conviction_tier


def test_investment_committee_fails_closed_on_missing_data():
    """Verify missing market price, targets, or downside floor fail closed with 0% sizing."""
    req = ResearchRequest(query="Investigate NODATA", ticker="NODATA")
    state = create_initial_state(req, case_id="case_nodata")
    state["market_context"] = {
        "addv_20d": {"value": 50_000_000.0},
        "cap_tier": "large",
    }
    state["consensus_snapshot"] = {
        "earnings_proximity_flag": "SAFE",
    }
    model = FakeCIOModel()

    # 1. Missing price
    updates = run_investment_committee(state, model=model)
    verdict = updates["ic_verdict"]
    assert verdict.verdict == "VALIDATION_WATCH"
    assert verdict.kelly_position_size_pct == 0.0
    assert "price_gate" in verdict.passing_discipline_checks

    # 2. Valid price, missing base target
    state["market_context"]["quote"] = {"price": 100.0}
    updates = run_investment_committee(state, model=model)
    verdict = updates["ic_verdict"]
    assert verdict.verdict == "VALIDATION_WATCH"
    assert verdict.kelly_position_size_pct == 0.0
    assert "target_gate" in verdict.passing_discipline_checks

    # 3. Valid target, missing bear floor
    state["consensus_snapshot"]["price_targets"] = {"mean": {"value": 150.0}}
    updates = run_investment_committee(state, model=model)
    verdict = updates["ic_verdict"]
    assert verdict.verdict == "VALIDATION_WATCH"
    assert verdict.kelly_position_size_pct == 0.0
    assert "bear_floor_gate" in verdict.passing_discipline_checks


def test_investment_committee_rejects_sub_3x_asymmetry():
    """Verify asymmetry below 3.0x strictly yields VALIDATION_WATCH and 0% allocation."""
    req = ResearchRequest(query="Investigate SUB3X", ticker="SUB3X")
    state = create_initial_state(req, case_id="case_sub3x")
    state["market_context"] = {
        "quote": {"price": 100.0},
        "addv_20d": {"value": 50_000_000.0},
        "cap_tier": "large",
    }
    state["consensus_snapshot"] = {
        "price_targets": {"mean": {"value": 125.0}},  # +25 upside
        "earnings_proximity_flag": "SAFE",
    }
    state["adversarial_report"] = AdversarialReport(
        ticker="SUB3X",
        falsifiable_objections=("Objection 1",),
        numeric_kill_criteria=("Kill 1",),
        bear_floor_price=90.0,  # 10 downside -> 25/10 = 2.5x (< 3.0x)
        bear_thesis_summary="Capex risk.",
    )
    model = FakeCIOModel()
    updates = run_investment_committee(state, model=model)
    verdict = updates["ic_verdict"]
    assert verdict.verdict == "VALIDATION_WATCH"
    assert verdict.reward_to_risk_ratio == pytest.approx(2.5)
    assert verdict.kelly_position_size_pct == 0.0
    assert "FAIL" in verdict.passing_discipline_checks["asymmetry_gate"]


def test_investment_committee_approves_via_bull_target_and_risk_budget():
    """Verify Bull Advocate target and stop-loss risk budget yield high-conviction approval."""
    from app.agent.bull import BullReport

    req = ResearchRequest(query="Investigate MU", ticker="MU", company="Micron")
    state = create_initial_state(req, case_id="case_mu_bull_approve")
    state["market_context"] = {
        "quote": {"price": 1000.0},
        "addv_20d": {"value": 50_000_000.0},
        "cap_tier": "large",
    }
    state["consensus_snapshot"] = {
        "price_targets": {"mean": {"value": 1200.0}},
        "earnings_proximity_flag": "SAFE",
    }
    state["bull_report"] = BullReport(
        ticker="MU",
        catalysts=("HBM expansion", "Margin inflection"),
        operating_leverage_drivers=("Fixed cost dilution",),
        bull_target_price=3000.0,  # 3.3x source-validated upside/downside fixture
        bull_thesis_summary="Massive unmodeled demand.",
        invalidation_conditions=(),
    )
    state["adversarial_report"] = AdversarialReport(
        ticker="MU",
        falsifiable_objections=("Capex risk",),
        numeric_kill_criteria=("Kill trigger",),
        bear_floor_price=400.0,  # Catastrophic -60% crash floor
        bear_thesis_summary="Capex destruction.",
    )
    state["confidence"] = 0.85

    model = FakeCIOModel()
    updates = run_investment_committee(state, model=model)

    verdict = updates["ic_verdict"]
    # Source-backed bear floor yields 2000 / 600 = 3.33x reward-to-risk.
    assert "APPROVED_LONG" in verdict.verdict
    assert verdict.reward_to_risk_ratio == pytest.approx(3.33)
    assert verdict.kelly_position_size_pct > 0.0
    assert "HIGH CONVICTION" in verdict.conviction_tier
