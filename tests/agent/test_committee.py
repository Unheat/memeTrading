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
