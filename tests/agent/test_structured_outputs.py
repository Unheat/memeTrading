"""Batch B acceptance tests: honest structured outputs (audit 2026-09-26).

Covers Fix 3 (deterministic implied growth + verdict), Fix 6 (bull target retry +
symmetric anchor fallbacks), Fix 7 (field-level tolerance, honest degraded statuses),
and Fix 10 (CIO payload anchor labeling).
"""
import json
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage

from app.agent.adversarial import run_adversarial_red_team, AdversarialReport
from app.agent.bull import run_bull_advocate
from app.agent.committee import run_investment_committee
from app.agent.contracts import BullCase
from app.agent.expectations import (
    _classify_expectation_gap,
    run_expectations_analyst,
)
from app.agent.state import ResearchRequest, create_initial_state


class _ScriptedModel:
    """Returns scripted responses in order; records invocation count."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        idx = min(self.calls - 1, len(self.responses) - 1)
        return AIMessage(content=self.responses[idx])


VALID_BULL_JSON = json.dumps({
    "catalysts": ["Catalyst 1", "Catalyst 2", "Catalyst 3"],
    "operating_leverage_drivers": ["Driver 1"],
    "bull_target_price": 120.0,
    "bull_thesis_summary": "Structural upside.",
    "invalidation_conditions": ["Condition 1"],
})
BULL_JSON_NO_TARGET = json.dumps({
    "catalysts": ["Catalyst 1", "Catalyst 2", "Catalyst 3"],
    "operating_leverage_drivers": ["Driver 1"],
    "bull_target_price": None,
    "bull_thesis_summary": "Structural upside.",
    "invalidation_conditions": ["Condition 1"],
})


def _diligence_state() -> dict:
    req = ResearchRequest(query="Analyze MU", ticker="MU", company="Micron")
    state = create_initial_state(req, case_id="case_structured_outputs")
    state["evidence"] = [{"quote": "Backlog secured", "source": "10-Q", "source_url": "https://sec.gov/x"}]
    state["market_context"] = {"quote": {"price": 100.0}}
    state["consensus_snapshot"] = {"price_targets": {"mean": {"value": 110.0}, "high": {"value": 140.0}}}
    return state


# --- Fix 6: bull advocate retry and honest statuses ----------------------------------

def test_bull_retry_recovers_missing_target():
    model = _ScriptedModel([BULL_JSON_NO_TARGET, VALID_BULL_JSON])
    result = run_bull_advocate(_diligence_state(), model)
    report = result["bull_report"]
    assert model.calls == 2
    assert report.status == "available"
    assert report.bull_target_price == pytest.approx(120.0)
    assert report.degradation_reasons == ()


def test_bull_degraded_when_target_missing_after_retry():
    model = _ScriptedModel([BULL_JSON_NO_TARGET])
    result = run_bull_advocate(_diligence_state(), model)
    report = result["bull_report"]
    assert model.calls == 2  # structured retry fired
    assert report.status == "degraded"
    assert report.bull_target_price is None
    assert report.catalysts  # valid fields preserved despite degraded target
    assert any("bull_target_price" in r for r in report.degradation_reasons)


def test_bull_unavailable_when_unparseable():
    model = _ScriptedModel(["total garbage {", "still not json"])
    result = run_bull_advocate(_diligence_state(), model)
    report = result["bull_report"]
    assert report.status == "unavailable"
    assert report.bull_target_price is None


# --- Fix 7: adversarial field-level tolerance ----------------------------------------

def test_bear_degrades_gracefully_on_malformed_field():
    payload = json.dumps({
        "falsifiable_objections": ["Objection 1", "Objection 2"],
        "numeric_kill_criteria": ["Kill 1", "Kill 2"],
        "bear_floor_price": "abc",  # malformed numeric field
        "bear_thesis_summary": "Bear case.",
    })
    result = run_adversarial_red_team(_diligence_state(), _ScriptedModel([payload]))
    report = result["adversarial_report"]
    assert report.status == "degraded"
    assert report.bear_floor_price is None
    assert report.falsifiable_objections == ("Objection 1", "Objection 2")  # fields preserved
    assert report.numeric_kill_criteria == ("Kill 1", "Kill 2")
    assert result["thesis_breakers"] == ["Kill 1", "Kill 2"]


def test_bear_available_with_valid_fields():
    payload = json.dumps({
        "falsifiable_objections": ["Objection 1"],
        "numeric_kill_criteria": ["Kill 1"],
        "bear_floor_price": 85.0,
        "bear_thesis_summary": "Bear case.",
    })
    result = run_adversarial_red_team(_diligence_state(), _ScriptedModel([payload]))
    report = result["adversarial_report"]
    assert report.status == "available"
    assert report.bear_floor_price == pytest.approx(85.0)


def test_bear_unavailable_on_garbage():
    result = run_adversarial_red_team(_diligence_state(), _ScriptedModel(["no json here"]))
    assert result["adversarial_report"].status == "unavailable"


# --- Fix 3: deterministic expectation-gap classification -----------------------------

def test_classify_expectation_gap_boundaries():
    assert _classify_expectation_gap(0.20, 0.10) == "ALREADY_PRICED_IN"
    assert _classify_expectation_gap(0.10, 0.20) == "HIDDEN_EXPECTATIONS_EDGE"
    assert _classify_expectation_gap(0.12, 0.13) == "BALANCED_PRICING"
    assert _classify_expectation_gap(None, 0.10) == "UNCERTAIN_DISPERSION"
    assert _classify_expectation_gap(0.10, None) == "UNCERTAIN_DISPERSION"


def test_expectations_fabricated_number_replaced_by_template():
    fabricated = json.dumps({
        "expectation_gap_verdict": "ALREADY_PRICED_IN",
        "expectation_gap_summary": "Market pricing looks demanding.",
        "implied_growth_interpretation": "The market prices in a 99.99% FCF CAGR immediately.",
        "dcf_assumptions": {
            "terminal_growth_rate": 0.025,
            "projection_years": 5,
            "low_case": {"fcf_growth_rate": 0.08, "discount_rate": 0.11},
            "base_case": {"fcf_growth_rate": 0.16, "discount_rate": 0.09},
            "high_case": {"fcf_growth_rate": 0.24, "discount_rate": 0.085},
        },
    })
    state = _diligence_state()
    state["market_context"] = {
        "quote": {"price": 100.0},
        "fundamentals": {"shares_outstanding": 1_000_000_000.0},
    }
    state["sec_financials"] = {
        "status": "ok",
        "periods": ["2026-Q2"],
        "cash_from_operations": {"2026-Q2": 4_000_000_000.0},
        "capex": {"2026-Q2": 2_000_000_000.0},
        "cash_and_equivalents": {"2026-Q2": 9_000_000_000.0},
        "total_debt": {"2026-Q2": 5_000_000_000.0},
    }
    result = run_expectations_analyst(state, model=_ScriptedModel([fabricated]))
    gap = result["expectation_gap"]
    assert gap["status"] == "degraded"
    assert any("conflicted_with_calculator" in r for r in gap["degradation_reasons"])
    assert gap["implied_growth_interpretation"].startswith("Deterministic reverse DCF")
    assert "99.99" not in gap["implied_growth_interpretation"]
    assert gap["implied_fcf_growth_rate"] is not None
    assert "99.99" not in gap["implied_growth_interpretation"]


# --- Fixes 6+10: committee anchor fallbacks and payload labeling ---------------------

def _committee_state(bull_report=None, bear_floor=85.0) -> dict:
    req = ResearchRequest(query="Investigate MU", ticker="MU", company="Micron")
    state = create_initial_state(req, case_id="case_structured_outputs_ic")
    state["market_context"] = {
        "quote": {"price": 100.0},
        "addv_20d": {"value": 50_000_000.0},
        "cap_tier": "large",
    }
    state["consensus_snapshot"] = {
        "price_targets": {"mean": {"value": 110.0}, "high": {"value": 140.0}},
        "earnings_proximity_flag": "SAFE",
    }
    state["adversarial_report"] = AdversarialReport(
        ticker="MU",
        falsifiable_objections=("Objection 1",),
        numeric_kill_criteria=("Kill 1",),
        bear_floor_price=bear_floor,
        bear_thesis_summary="Bear case.",
    )
    if bull_report is not None:
        state["bull_report"] = bull_report
    return state


def test_committee_uses_consensus_high_fallback_when_bull_degraded():
    bull = BullCase(ticker="MU", status="degraded", bull_target_price=None)
    state = _committee_state(bull_report=bull)
    # Street mean below price (no upside anchor from mean/bull) -> escalate to Street high.
    state["consensus_snapshot"]["price_targets"] = {
        "mean": {"value": 95.0},
        "high": {"value": 140.0},
        "earnings_proximity_flag": "SAFE",
    }
    verdict = run_investment_committee(state, model=_ScriptedModel(["not json"]))["ic_verdict"]
    assert verdict.upside_anchor == pytest.approx(140.0)
    assert verdict.upside_anchor_source == "consensus_high_fallback"
    assert verdict.bear_anchor_source == "red_team_bear_floor"


def test_committee_prefers_bull_target_when_available():
    bull = BullCase(ticker="MU", bull_target_price=800.0)
    state = _committee_state(bull_report=bull)
    verdict = run_investment_committee(state, model=_ScriptedModel(["not json"]))["ic_verdict"]
    assert verdict.upside_anchor == pytest.approx(800.0)
    assert verdict.upside_anchor_source == "bull_target_price"


def test_committee_falls_back_to_dcf_low_for_bear_floor():
    bull = BullCase(ticker="MU", bull_target_price=800.0)
    state = _committee_state(bull_report=bull, bear_floor=None)
    state["quant_report"] = {
        "valuation": {"fair_value_range": {"low": 70.0, "base": 90.0, "high": 120.0}}
    }
    verdict = run_investment_committee(state, model=_ScriptedModel(["not json"]))["ic_verdict"]
    assert verdict.bear_anchor_source == "dcf_low_fallback"
    # ratio uses fallback floor: (800-100)/(100-70) = 23.33
    assert verdict.reward_to_risk_ratio == pytest.approx(23.33)
