"""Tests for Scuttlebutt channel checks and 3-way expectation arbitrage upgrades.

Covers:
1. ChannelCheckReceipt / ChannelCheckReport schema validation (contracts).
2. channel_check_primary evidence tier acceptance (planning).
3. run_channel_check_analysis deterministic verdicts (specialists).
4. Diligence dossier carries the channel report.
5. run_expectations_analyst arbitrage fields + memo arbitrage block.
"""
from __future__ import annotations

import json

import pytest
from langchain_core.messages import AIMessage
from pydantic import ValidationError

from app.agent.contracts import ChannelCheckReceipt, ChannelCheckReport
from app.agent.diligence import build_diligence_dossier, run_candidate_diligence
from app.agent.expectations import (
    _classify_expectation_arbitrage,
    run_expectations_analyst,
)
from app.agent.memo import render_forensic_memo
from app.agent.planning import ResearchHypothesis
from app.agent.specialists import run_channel_check_analysis
from app.agent.state import ResearchRequest, create_initial_state


class FakeExpectationsModel:
    """Mock valuation modeler returning structured JSON without conflicting numbers."""

    def invoke(self, messages):
        return AIMessage(content=json.dumps({
            "expectation_gap_verdict": "UNDERPRICED_CATALYST",
            "expectation_gap_summary": "Channel telemetry shows acceleration.",
            "implied_growth_interpretation": "Qualitative commentary without numbers.",
            "dcf_assumptions": {
                "terminal_growth_rate": 0.025,
                "projection_years": 5,
                "low_case": {"fcf_growth_rate": -0.04, "discount_rate": 0.11},
                "base_case": {"fcf_growth_rate": 0.09, "discount_rate": 0.095},
                "high_case": {"fcf_growth_rate": 0.20, "discount_rate": 0.085},
            },
        }))


class FakeNoopModel:
    """Model used by the channel specialist narrative path."""

    def invoke(self, messages):
        return AIMessage(content="Distributor stockouts confirm accelerating demand momentum.")


# ---------------------------------------------------------------------------
# R1: Contract schemas
# ---------------------------------------------------------------------------


def test_channel_check_receipt_validates_and_serializes():
    receipt = ChannelCheckReceipt(
        receipt_id="cc_mu_digikey_01",
        channel_type="distributor_inventory",
        source_url_or_channel="https://www.digikey.com/en/products/filter/dram",
        target_ticker="mu",
        observed_metric="DDR5_lead_time_weeks",
        observed_value=24.0,
        baseline_value=8.0,
        implication="bullish_inflection",
        quote_or_evidence="Lead times extended to 24 weeks from 8.",
        observed_at_utc="2026-10-01T00:00:00+00:00",
    )
    data = receipt.to_dict()
    assert data["target_ticker"] == "MU"
    assert data["implication"] == "bullish_inflection"
    assert data["receipt_id"] == "cc_mu_digikey_01"


def test_channel_check_receipt_rejects_invalid_channel_type():
    with pytest.raises(ValidationError):
        ChannelCheckReceipt(
            receipt_id="cc_bad",
            channel_type="twitter_vibes",
            source_url_or_channel="https://x.com",
            target_ticker="MU",
            observed_metric="vibes",
            observed_value="high",
        )


def test_channel_check_report_defaults_to_insufficient():
    report = ChannelCheckReport(ticker="MU")
    data = report.to_dict()
    assert data["status"] == "insufficient_data"
    assert data["channel_verdict"] == "INSUFFICIENT_CHANNEL_DATA"
    assert data["channel_implied_growth"] is None
    assert data["receipts_count"] == 0


# ---------------------------------------------------------------------------
# R2: Planner tier
# ---------------------------------------------------------------------------


def test_research_hypothesis_accepts_channel_check_tier():
    hyp = ResearchHypothesis(
        statement="Are DDR5 distributor lead times extending ahead of earnings?",
        evidence_tier="channel_check_primary",
        target_entity="MU",
    )
    assert hyp.evidence_tier == "channel_check_primary"


def test_research_hypothesis_still_rejects_unknown_tiers():
    with pytest.raises(ValidationError):
        ResearchHypothesis(statement="x", evidence_tier="vibes")


# ---------------------------------------------------------------------------
# R3: Channel specialist verdicts
# ---------------------------------------------------------------------------


def _receipt(metric: str, implication: str, value: float = 1.0) -> dict:
    return {
        "receipt_id": f"cc_test_{metric}",
        "channel_type": "distributor_inventory",
        "source_url_or_channel": "https://example.com/channel",
        "observed_metric": metric,
        "observed_value": value,
        "implication": implication,
        "quote_or_evidence": f"{metric} observation",
    }


def test_channel_check_insufficient_with_zero_observations():
    req = ResearchRequest(query="Analyze MU", ticker="MU", company="Micron")
    state = create_initial_state(req, case_id="case_mu")
    result = run_channel_check_analysis(state, model=None)
    report = result["channel_check_report"]
    assert report["status"] == "insufficient_data"
    assert report["channel_verdict"] == "INSUFFICIENT_CHANNEL_DATA"
    assert report["receipts_count"] == 0


def test_channel_check_acceleration_with_bullish_receipts():
    req = ResearchRequest(query="Analyze MU", ticker="MU", company="Micron")
    state = create_initial_state(req, case_id="case_mu")
    state["channel_check_receipts"] = [
        _receipt("dram_spot_price", "bullish_inflection"),
        _receipt("ddr5_lead_time", "bullish_inflection"),
    ]
    result = run_channel_check_analysis(state, model=None)
    report = result["channel_check_report"]
    assert report["status"] == "available"
    assert report["channel_verdict"] == "CHANNEL_ACCELERATION"
    assert report["bullish_count"] == 2
    assert report["discordant_signals"] == 0


def test_channel_check_breakdown_with_bearish_receipts():
    req = ResearchRequest(query="Analyze ESTC", ticker="ESTC", company="Elastic")
    state = create_initial_state(req, case_id="case_estc")
    state["channel_check_receipts"] = [
        _receipt("github_star_growth", "bearish_inflection"),
        _receipt("seat_downgrades", "bearish_inflection"),
    ]
    result = run_channel_check_analysis(state, model=None)
    report = result["channel_check_report"]
    assert report["channel_verdict"] == "CHANNEL_BREAKDOWN"
    assert report["bearish_count"] == 2


def test_channel_check_mixed_when_conflicting():
    req = ResearchRequest(query="Analyze MU", ticker="MU", company="Micron")
    state = create_initial_state(req, case_id="case_mu")
    state["channel_check_receipts"] = [
        _receipt("spot_price", "bullish_inflection"),
        _receipt("churn_chatter", "bearish_inflection"),
        _receipt("lead_times", "bullish_inflection"),
        _receipt("inventory", "bearish_inflection"),
    ]
    result = run_channel_check_analysis(state, model=None)
    report = result["channel_check_report"]
    assert report["channel_verdict"] == "MIXED_CHANNEL"
    assert report["discordant_signals"] == 2


def test_channel_check_normalizes_social_signal_payload():
    req = ResearchRequest(query="Analyze MU", ticker="MU", company="Micron")
    state = create_initial_state(req, case_id="case_mu")
    state["capability_outputs"] = {
        "social_signal": {
            "trend_metrics": {"velocity_24h": {"value": 3.2}, "mentions": {"value": 120}},
        }
    }
    result = run_channel_check_analysis(state, model=None)
    report = result["channel_check_report"]
    assert report["receipts_count"] >= 2
    metrics = {r["observed_metric"]: r["implication"] for r in report["receipts"]}
    assert metrics.get("social_mention_velocity_24h") == "bullish_inflection"
    assert metrics.get("social_mentions") == "neutral"
    # Spec rule: 1 bullish + 1 neutral observation -> MIXED_CHANNEL (only one
    # directional receipt; acceleration requires 2+ concordant directional signals).
    assert report["channel_verdict"] == "MIXED_CHANNEL"


def test_channel_check_model_fails_but_report_stays_deterministic():
    class ExplodingModel:
        def invoke(self, messages):
            raise RuntimeError("provider down")

    req = ResearchRequest(query="Analyze MU", ticker="MU", company="Micron")
    state = create_initial_state(req, case_id="case_mu")
    state["channel_check_receipts"] = [
        _receipt("spot_price", "bullish_inflection"),
        _receipt("lead_time", "bullish_inflection"),
    ]
    result = run_channel_check_analysis(state, model=ExplodingModel())
    report = result["channel_check_report"]
    assert report["channel_verdict"] == "CHANNEL_ACCELERATION"
    assert report["status"] == "degraded"
    assert report["synthesis_summary"] == ""


def test_channel_check_model_narrative_only_summary():
    req = ResearchRequest(query="Analyze MU", ticker="MU", company="Micron")
    state = create_initial_state(req, case_id="case_mu")
    state["channel_check_receipts"] = [
        _receipt("spot_price", "bullish_inflection"),
        _receipt("lead_time", "bullish_inflection"),
    ]
    result = run_channel_check_analysis(state, model=FakeNoopModel())
    report = result["channel_check_report"]
    assert "stockouts" in report["synthesis_summary"]
    # Counts stay deterministic regardless of narrative
    assert report["bullish_count"] == 2


def test_diligence_dossier_includes_channel_report():
    cand_state = {
        "ticker": "MU",
        "company": "Micron",
        "quant_report": {"valuation": {"implied_fcf_growth_rate": -0.08}},
        "forensic_report": {"verdict": "CLEAN_INVESTMENT_GRADE"},
        "moat_report": {"analysis": {"moat_rating": "WIDE"}},
        "channel_check_report": {
            "ticker": "MU",
            "status": "available",
            "receipts_count": 3,
            "bullish_count": 3,
            "bearish_count": 0,
            "channel_verdict": "CHANNEL_ACCELERATION",
        },
    }
    dossier = build_diligence_dossier(cand_state, None, None, "cand_mu", "MU")
    assert dossier["channel_check_report"]["channel_verdict"] == "CHANNEL_ACCELERATION"


# ---------------------------------------------------------------------------
# R4: 3-way expectation arbitrage
# ---------------------------------------------------------------------------


def test_arbitrage_classifier_unpriced_acceleration():
    delta, verdict = _classify_expectation_arbitrage(-0.04, 0.09, 0.25, "CHANNEL_ACCELERATION")
    assert verdict == "UNPRICED_CHANNEL_ACCELERATION"
    assert delta == pytest.approx(0.25 - 0.09)


def test_arbitrage_classifier_breakdown_short():
    delta, verdict = _classify_expectation_arbitrage(0.30, 0.25, 0.05, "CHANNEL_BREAKDOWN")
    assert verdict == "CHANNEL_BREAKDOWN_SHORT"
    assert delta == pytest.approx(0.05 - 0.30)


def test_arbitrage_classifier_verdict_only_paths():
    _, verdict = _classify_expectation_arbitrage(-0.04, None, None, "CHANNEL_ACCELERATION")
    assert verdict == "UNPRICED_CHANNEL_ACCELERATION"
    _, verdict = _classify_expectation_arbitrage(0.50, None, None, "CHANNEL_BREAKDOWN")
    assert verdict == "PRICED_TO_PERFECTION"
    _, verdict = _classify_expectation_arbitrage(None, None, None, None)
    assert verdict == "UNCERTAIN_DISPERSION"


def test_expectations_analyst_includes_arbitrage_fields():
    req = ResearchRequest(query="Analyze MU", ticker="MU", company="Micron")
    state = create_initial_state(req, case_id="case_mu")
    state["market_context"] = {
        "quote": {"price": 100.0},
        "fundamentals": {"shares_outstanding": 1_000_000_000.0},
    }
    state["consensus_snapshot"] = {
        "eps_estimates": [{"metric": "eps", "growth": 0.15}],
        "revenue_estimates": [{"metric": "revenue", "growth": 0.12}],
    }
    state["sec_financials"] = {
        "status": "ok",
        "periods": ["2026-Q2"],
        "cash_from_operations": {"2026-Q2": 4_000_000_000.0},
        "capex": {"2026-Q2": 2_000_000_000.0},
        "ttm_fcf": 2_000_000_000.0,
    }
    state["channel_check_report"] = {
        "ticker": "MU",
        "status": "available",
        "receipts_count": 3,
        "channel_implied_growth": 0.25,
        "channel_verdict": "CHANNEL_ACCELERATION",
    }

    result = run_expectations_analyst(state, model=FakeExpectationsModel())
    gap = result["expectation_gap"]
    assert gap["channel_growth_estimate"] == 0.25
    assert gap["arbitrage_delta"] is not None
    assert gap["arbitrage_verdict"] in {
        "UNPRICED_CHANNEL_ACCELERATION", "CONSENSUS_ALIGNED", "CHANNEL_BREAKDOWN_SHORT",
    }


def test_expectations_analyst_without_channel_report_regression_safe():
    req = ResearchRequest(query="Analyze MU", ticker="MU", company="Micron")
    state = create_initial_state(req, case_id="case_mu")
    state["market_context"] = {
        "quote": {"price": 100.0},
        "fundamentals": {"shares_outstanding": 1_000_000_000.0},
    }
    state["consensus_snapshot"] = {
        "eps_estimates": [{"metric": "eps", "growth": 0.15}],
        "revenue_estimates": [{"metric": "revenue", "growth": 0.12}],
    }
    state["sec_financials"] = {
        "status": "ok",
        "periods": ["2026-Q2"],
        "cash_from_operations": {"2026-Q2": 4_000_000_000.0},
        "capex": {"2026-Q2": 2_000_000_000.0},
        "ttm_fcf": 2_000_000_000.0,
    }

    result = run_expectations_analyst(state, model=FakeExpectationsModel())
    gap = result["expectation_gap"]
    assert gap["channel_growth_estimate"] is None
    assert gap["arbitrage_delta"] is None
    assert gap["arbitrage_verdict"] == "UNCERTAIN_DISPERSION"
    assert gap["verdict"] == "ALREADY_PRICED_IN"


# ---------------------------------------------------------------------------
# R4: Memo arbitrage block
# ---------------------------------------------------------------------------


def _memo_state_with_channel() -> dict:
    req = ResearchRequest(query="Analyze MU", ticker="MU", company="Micron")
    state = create_initial_state(req, case_id="case_mu")
    state["status"] = "completed"
    state["channel_check_report"] = {
        "ticker": "MU",
        "status": "available",
        "receipts": [_receipt("spot_price", "bullish_inflection"), _receipt("lead_time", "bullish_inflection")],
        "receipts_count": 2,
        "bullish_count": 2,
        "bearish_count": 0,
        "discordant_signals": 0,
        "channel_implied_growth": 0.25,
        "channel_verdict": "CHANNEL_ACCELERATION",
        "synthesis_summary": "Distributor stockouts confirm accelerating demand.",
    }
    state["expectation_gap"] = {
        "verdict": "HIDDEN_EXPECTATIONS_EDGE",
        "implied_fcf_growth_rate": -0.04,
        "consensus_growth_estimate": 0.09,
        "expectation_edge": 0.13,
        "arbitrage_delta": 0.16,
        "arbitrage_verdict": "UNPRICED_CHANNEL_ACCELERATION",
    }
    state["forensic_report"] = {"verdict": "CLEAN_INVESTMENT_GRADE"}
    return state


def test_memo_renders_arbitrage_block_when_channel_report_exists():
    memo = render_forensic_memo(_memo_state_with_channel(), final_text="")
    assert "Expectation Arbitrage (3-Pillar Synthesis)" in memo
    assert "CHANNEL_ACCELERATION" in memo
    assert "UNPRICED_CHANNEL_ACCELERATION" in memo
    assert "Distributor stockouts confirm accelerating demand." in memo


def test_memo_omits_arbitrage_block_without_channel_report():
    req = ResearchRequest(query="Analyze MU", ticker="MU", company="Micron")
    state = create_initial_state(req, case_id="case_mu")
    state["status"] = "completed"
    memo = render_forensic_memo(state, final_text="")
    assert "Expectation Arbitrage (3-Pillar Synthesis)" not in memo
