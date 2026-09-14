"""Tests for the air-gapped adversarial red team node."""
from unittest.mock import MagicMock
import pytest
from langchain_core.messages import AIMessage
from app.agent.state import ResearchRequest, create_initial_state
from app.agent.adversarial import run_adversarial_red_team, AdversarialReport


class FakeRedTeamModel:
    """Mock model that returns structured short-seller attacks."""

    def invoke(self, messages):
        return AIMessage(
            content="""{
  "falsifiable_objections": [
    "DDR5 spot price premium will compress as Samsung and SK Hynix ramp 1b-nm nodes in Q3.",
    "Capex expansion of $12B will depress normalized Free Cash Flow margin below 15%.",
    "Customer concentration risk: top 3 cloud hyperscalers account for 48% of high-bandwidth revenue.",
    "China export licensing restrictions could eliminate 14% of trailing regional shipments."
  ],
  "numeric_kill_criteria": [
    "Kill Trigger 1: Quarterly gross margin contracts below 30.0% in next 10-Q.",
    "Kill Trigger 2: Days Sales of Inventory (DSI) rises by more than 15 days QoQ."
  ],
  "bear_floor_price": 75.0,
  "bear_thesis_summary": "Cyclical commodity trap: peak margin illusion with high capex burdens."
}"""
        )


def test_adversarial_red_team_execution():
    req = ResearchRequest(query="Investigate MU DDR5 boom", ticker="MU", company="Micron")
    state = create_initial_state(req, case_id="case_mu_red")
    state["evidence"] = [
        {"form": "10-Q", "quote": "Gross margin expanded to 36%", "verdict": "CONFIRMED"}
    ]

    model = FakeRedTeamModel()
    updates = run_adversarial_red_team(state, model=model)

    assert "thesis_breakers" in updates
    assert len(updates["thesis_breakers"]) >= 2
    assert "Kill Trigger 1" in updates["thesis_breakers"][0]

    report = updates.get("adversarial_report")
    assert isinstance(report, AdversarialReport)
    assert report.ticker == "MU"
    assert len(report.falsifiable_objections) == 4
    assert len(report.numeric_kill_criteria) == 2
    assert report.bear_floor_price == 75.0
    assert "Cyclical commodity trap" in report.bear_thesis_summary
