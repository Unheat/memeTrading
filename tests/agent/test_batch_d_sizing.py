"""Batch D acceptance tests: tiered sizing + profitability measurement (audit 2026-09-26).

Covers the mandate-style hurdle profiles, tiered Kelly sizing (paper-trade watch,
quarter-Kelly, half-Kelly), the expectation-edge ranking metric, and the backtest
scorer's calibration math on synthetic cases.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.config import effective_asymmetry_hurdle
from app.agent.adversarial import AdversarialReport
from app.agent.committee import run_investment_committee
from app.agent.contracts import BullCase
from app.agent.screening import build_candidate_comparisons
from app.agent.state import ResearchRequest, create_initial_state
from tools.backtest_score import load_case_records, score_cases


class _EchoCIO:
    """CIO mock whose unparseable text triggers the deterministic fallback path."""

    def invoke(self, messages):
        return type("R", (), {"content": "no json"})()


def _committee_state(price=100.0, mean=110.0, floor=85.0, bull_target=None) -> dict:
    req = ResearchRequest(query="Investigate MU", ticker="MU", company="Micron")
    state = create_initial_state(req, case_id="case_batch_d")
    state["market_context"] = {
        "quote": {"price": price},
        "addv_20d": {"value": 50_000_000.0},
        "cap_tier": "large",
    }
    state["consensus_snapshot"] = {
        "price_targets": {"mean": {"value": mean}, "high": {"value": mean * 1.3}},
        "earnings_proximity_flag": "SAFE",
    }
    state["adversarial_report"] = AdversarialReport(
        ticker="MU", falsifiable_objections=("O1",), numeric_kill_criteria=("K1",),
        bear_floor_price=floor, bear_thesis_summary="Bear.",
    )
    if bull_target is not None:
        state["bull_report"] = BullCase(ticker="MU", bull_target_price=bull_target)
    return state


# --- Config: mandate style profiles ---------------------------------------------------

def test_mandate_style_hurdle_profiles():
    assert effective_asymmetry_hurdle({"mandate_style": "deep_value"}) == pytest.approx(3.0)
    assert effective_asymmetry_hurdle({"mandate_style": "compounder"}) == pytest.approx(2.0)
    assert effective_asymmetry_hurdle({"mandate_style": "momo"}) == pytest.approx(4.0)
    assert effective_asymmetry_hurdle({"mandate_style": "momo", "asymmetry_hurdle": 2.5}) == pytest.approx(2.5)
    assert effective_asymmetry_hurdle({}) == pytest.approx(3.0)  # default


# --- Tiered sizing ---------------------------------------------------------------------

def test_paper_trade_tier_between_two_and_three_x():
    # ratio = (110-100)/(100-95) = 2.0 -> paper trade, zero capital
    verdict = run_investment_committee(_committee_state(mean=110.0, floor=95.0), model=_EchoCIO())["ic_verdict"]
    assert verdict.verdict == "PAPER_TRADE_WATCH"
    assert verdict.paper_trade is True
    assert verdict.kelly_position_size_pct == pytest.approx(0.0)


def test_validation_watch_below_paper_trade_ratio():
    # ratio = (110-100)/(100-85) = 0.67 -> below paper-trade floor
    verdict = run_investment_committee(_committee_state(mean=110.0, floor=85.0), model=_EchoCIO())["ic_verdict"]
    assert verdict.verdict == "VALIDATION_WATCH"
    assert verdict.paper_trade is False
    assert verdict.kelly_position_size_pct == pytest.approx(0.0)


def test_quarter_kelly_tier_for_standard_approval():
    # bull target 160: ratio = (160-100)/15 = 4.0 >= hurdle 3 but < half-Kelly 5
    verdict = run_investment_committee(_committee_state(bull_target=160.0), model=_EchoCIO())["ic_verdict"]
    assert "APPROVED_LONG" in verdict.verdict
    assert verdict.kelly_position_size_pct == pytest.approx(0.08)  # quarter-tier cap


def test_half_kelly_tier_for_exceptional_asymmetry():
    # bull target 800: ratio = (800-100)/15 = 46.7 >= half-Kelly 5, reports clean
    verdict = run_investment_committee(_committee_state(bull_target=800.0), model=_EchoCIO())["ic_verdict"]
    assert "APPROVED_LONG" in verdict.verdict
    assert verdict.kelly_position_size_pct == pytest.approx(0.10)  # half-tier cap


# --- Expectation-edge ranking metric ---------------------------------------------------

def test_comparison_cards_include_expectation_edge():
    candidates = {
        "cand_a": {
            "candidate_id": "cand_a",
            "ticker": "AAAA",
            "market_context": {"quote": {"price": 100.0}},
            "sec_financials": {"status": "ok", "periods": ["2026-Q2"]},
            "consensus_snapshot": {"revenue_estimates": [{"metric": "revenue", "growth": 0.20}]},
            "diligence_dossier": {"expectation_gap": {"implied_fcf_growth_rate": 0.12}},
        },
        "cand_b": {
            "candidate_id": "cand_b",
            "ticker": "BBBB",
            "market_context": {"quote": {"price": 50.0}},
            "sec_financials": {"status": "ok", "periods": ["2026-Q2"]},
            "consensus_snapshot": {"revenue_estimates": [{"metric": "revenue", "growth": 0.05}]},
            "diligence_dossier": {"expectation_gap": {"implied_fcf_growth_rate": 0.30}},
        },
    }
    cards = build_candidate_comparisons(candidates, ["cand_a", "cand_b"], metrics=["expectation_edge"])
    edge_card = next(c for c in cards if c.get("metric_key") == "expectation_edge")
    assert edge_card["candidate_values"]["AAAA"]["value"] == pytest.approx(0.08)   # +edge: underpriced expectations
    assert edge_card["candidate_values"]["BBBB"]["value"] == pytest.approx(-0.25)  # negative edge: already priced in


# --- Backtest scorer -------------------------------------------------------------------

def _write_case(root: Path, case_id: str, ticker: str, price: float, verdict: str, anchor: float | None, created: str) -> None:
    case_dir = root / case_id
    case_dir.mkdir(parents=True)
    payload = {
        "case_id": case_id,
        "ticker": ticker,
        "created_at": created,
        "market_context": {"quote": {"price": price}},
        "ic_verdict": {
            "verdict": verdict,
            "reward_to_risk_ratio": 4.0,
            "upside_anchor": anchor,
            "kelly_position_size_pct": 0.08 if verdict.startswith("APPROVED") else 0.0,
            "paper_trade": verdict.startswith("PAPER"),
            "bear_floor": price * 0.85,
        },
    }
    (case_dir / "investigation.json").write_text(json.dumps(payload), encoding="utf-8")


def test_backtest_scorer_calibration_on_synthetic_cases(tmp_path: Path):
    _write_case(tmp_path, "A-2026-01-01-001", "WIN", 100.0, "APPROVED_LONG_HIGH", 130.0, "2026-01-15T10:00:00+00:00")
    _write_case(tmp_path, "B-2026-01-01-002", "LOSE", 100.0, "VALIDATION_WATCH", 110.0, "2026-01-15T10:00:00+00:00")

    def fake_provider(ticker: str, start: datetime, end: datetime) -> float | None:
        return {"WIN": 120.0, "LOSE": 90.0}.get(ticker)

    records = load_case_records(tmp_path)
    assert len(records) == 2
    report = score_cases(records, fake_provider, horizons=(63,))
    approved = report["buckets"]["approved"]["h63"]
    rejected = report["buckets"]["no_position"]["h63"]
    assert approved["hit_rate"] == pytest.approx(1.0)
    assert approved["avg_forward_return"] == pytest.approx(0.20)
    assert approved["avg_predicted_upside"] == pytest.approx(0.30)
    assert approved["calibration_error"] == pytest.approx(0.10)  # over-promised by 10pts
    assert rejected["avg_forward_return"] == pytest.approx(-0.10)
    assert report["total_cases"] == 2


def test_backtest_scorer_skips_unscoreable_cases(tmp_path: Path):
    (tmp_path / "EMPTY-001").mkdir()
    (tmp_path / "EMPTY-001" / "investigation.json").write_text(json.dumps({"case_id": "EMPTY-001"}), encoding="utf-8")
    assert load_case_records(tmp_path) == []
