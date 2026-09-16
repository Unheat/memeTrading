"""Tests for the air-gapped Bull Case Advocate node."""
from unittest.mock import MagicMock
import pytest
from langchain_core.messages import AIMessage
from app.agent.bull import run_bull_advocate, BullReport
from app.agent.state import ResearchRequest, create_initial_state


class FakeBullModel:
    """Mock model generating structured bull case JSON."""

    def invoke(self, messages):
        return AIMessage(
            content="""```json
{
  "catalysts": [
    "HBM3E memory ramp drives 350 bps gross margin expansion.",
    "Enterprise AI server backlog committed through 2027.",
    "Bespoke custom silicon partnerships expand ASP by 20%."
  ],
  "operating_leverage_drivers": [
    "Fixed fab depreciation absorbed by outsized bit shipment volume.",
    "High-margin packaging mix shift expands operating leverage."
  ],
  "bull_target_price": 1650.0,
  "bull_thesis_summary": "Wall Street models underestimate structural HBM pricing power.",
  "invalidation_conditions": [
    "Enterprise capex pauses or hyperscaler cancellation rates exceed 10%."
  ]
}
```"""
        )


def test_bull_advocate_parses_catalysts_and_target():
    """Verify bull advocate parses catalysts, drivers, and upside price target."""
    req = ResearchRequest(query="Investigate MU", ticker="MU", company="Micron")
    state = create_initial_state(req, case_id="case_mu_bull")
    state["market_context"] = {
        "quote": {"price": 925.0},
        "returns": {"1m": {"value": 0.05}},
    }
    state["consensus_snapshot"] = {
        "price_targets": {"mean": {"value": 1500.0}},
    }

    model = FakeBullModel()
    updates = run_bull_advocate(state, model=model)

    assert "bull_report" in updates
    report = updates["bull_report"]
    assert isinstance(report, BullReport)
    assert report.ticker == "MU"
    assert len(report.catalysts) == 3
    assert report.bull_target_price == 1650.0
    assert "pricing power" in report.bull_thesis_summary


def test_bull_advocate_falls_back_on_malformed_json():
    """Verify malformed model response gracefully falls back to consensus baseline."""
    req = ResearchRequest(query="Investigate FALLBACK", ticker="FALLBACK")
    state = create_initial_state(req, case_id="case_fallback")
    state["consensus_snapshot"] = {
        "price_targets": {"mean": {"value": 120.0}},
    }

    failing_model = MagicMock()
    failing_model.invoke.side_effect = RuntimeError("LLM timeout")

    updates = run_bull_advocate(state, model=failing_model)
    report = updates["bull_report"]
    assert isinstance(report, BullReport)
    assert report.ticker == "FALLBACK"
    assert report.bull_target_price is None
    assert report.catalysts == ()
