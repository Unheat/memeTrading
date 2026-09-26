"""Batch A acceptance tests: valuation single-source truth (audit 2026-09-26).

Covers Fix 1 (growth assumptions actually drive DCF flows), Fix 2 (evaluate_valuation
inherits expectation-gap/macro and reconciles with diligence), Fix 4 (Beneish published
coefficients), and Fix 8 (non-vacuous reproducibility verification).
"""
import json
from pathlib import Path

import pytest

from app.agent.specialists import run_quant_analysis
from app.agent.tools import create_agent_tools
from app.valuation.engine import run_calculator


# --- Fix 4: Beneish published coefficients -------------------------------------------

BENEISH_PROFILE_MANIPULATOR = {
    "dsri": 1.2, "gmi": 1.05, "aqi": 1.15, "sgi": 1.3,
    "depi": 1.05, "sgai": 0.95, "tata": 0.08, "lvgi": 1.15,
}
BENEISH_PROFILE_CLEAN = {
    "dsri": 0.95, "gmi": 0.98, "aqi": 1.0, "sgi": 1.15,
    "depi": 1.0, "sgai": 1.0, "tata": 0.02, "lvgi": 0.85,
}


def test_beneish_published_coefficients_hand_computed():
    """Lock the published 1999 coefficients with a hand-computed score."""
    from app.market.forensics import compute_beneish_m_score

    indices = {**BENEISH_PROFILE_CLEAN, "tata": 0.1, "lvgi": 1.2}
    expected = (
        -4.84
        + 0.92 * indices["dsri"] + 0.528 * indices["gmi"] + 0.404 * indices["aqi"]
        + 0.892 * indices["sgi"] + 0.115 * indices["depi"] - 0.172 * indices["sgai"]
        + 4.679 * indices["tata"] - 0.327 * indices["lvgi"]
    )
    result = compute_beneish_m_score(**indices)
    assert result["m_score"] == pytest.approx(expected, abs=1e-3)


def test_beneish_lvgi_is_negative_weight():
    """Rising leverage must LOWER the M-Score per the published model."""
    from app.market.forensics import compute_beneish_m_score

    base = dict(BENEISH_PROFILE_MANIPULATOR)
    levered = {**base, "lvgi": base["lvgi"] + 0.5}
    assert compute_beneish_m_score(**levered)["m_score"] < compute_beneish_m_score(**base)["m_score"]


def test_beneish_audit_profiles_verdicts():
    """Manipulator-like profile flags, clean fortress stays clean under the fixed model."""
    from app.market.forensics import compute_beneish_m_score

    assert compute_beneish_m_score(**BENEISH_PROFILE_MANIPULATOR)["is_manipulator_probability_high"] is True
    assert compute_beneish_m_score(**BENEISH_PROFILE_CLEAN)["is_manipulator_probability_high"] is False


# --- Fix 1: growth assumptions drive DCF flows ---------------------------------------

def _capex_spike_state(growth: float = 0.16, discount: float = 0.09) -> dict:
    """Build a minimal capex-spike research state with authored expectations."""
    return {
        "ticker": "TEST",
        "market_context": {
            "quote": {"price": 50.0, "previous_close": 49.5},
            "fundamentals": {"shares_outstanding": {"value": 1_000_000_000, "reliable": True}, "beta": {"value": 1.1}},
        },
        "sec_financials": {
            "status": "ok",
            "periods": ["Q1 2026"],
            "revenue": {"Q1 2026": 200_000_000.0},
            "cash_from_operations": {"Q1 2026": 100_000_000.0},
            "capex": {"Q1 2026": 80_000_000.0},
            "cash_and_equivalents": {"Q1 2026": 300_000_000.0},
            "total_debt": {"Q1 2026": 100_000_000.0},
        },
        "expectation_gap": {
            "terminal_growth_rate": 0.025,
            "projection_years": 5,
            "assumptions": {
                "low": {"growth": 0.08, "discount": 0.105},
                "base": {"growth": growth, "discount": discount},
                "high": {"growth": 0.24, "discount": 0.085},
            },
        },
    }


def test_quant_flows_follow_authored_growth_in_capex_spike_regime():
    """Fix 1: capex-spike regime must not override the analyst's growth assumptions."""
    report = run_quant_analysis(_capex_spike_state(growth=0.16))
    assert report["quant_report"]["status"] == "available"
    valuation = report["quant_report"]["valuation"]
    flows = valuation["cases"]["base"]["flows"]
    assert report["quant_report"]["assumptions"]["base_case_fcf_growth_rate"] == pytest.approx(0.16)
    # year2 / year1 must reflect (1+g): the ladder would give 1.15/1.05 ≈ 1.0952
    ratio = flows[1]["fcf"] / flows[0]["fcf"]
    assert ratio == pytest.approx(1.16, rel=1e-6)


def test_quant_fair_value_monotonic_in_case_growth():
    """Fix 1 acceptance: fair value strictly increases with case growth."""
    values = []
    for growth in (0.08, 0.16, 0.24):
        report = run_quant_analysis(_capex_spike_state(growth=growth))
        values.append(report["quant_report"]["valuation"]["cases"]["base"]["fair_value_per_share"])
    assert values[0] < values[1] < values[2]


# --- Fix 8: reproducibility verification actually compares ---------------------------

def _base_model() -> dict:
    return {
        "inputs": {"current_price": 50.0, "fcf_base": 280_000_000.0, "shares_diluted": 1_000_000_000, "net_cash": 200_000_000.0},
        "dcf": {
            "terminal_growth_rate": 0.025,
            "projection_years": 5,
            "cases": [
                {"case": "low", "fcf_growth_rate": 0.08, "discount_rate": 0.105},
                {"case": "base", "fcf_growth_rate": 0.16, "discount_rate": 0.09},
                {"case": "high", "fcf_growth_rate": 0.24, "discount_rate": 0.085},
            ],
        },
    }


def test_verify_passes_with_injected_stored_values():
    model = _base_model()
    computed = run_calculator(model)
    assert computed["status"] == "ok"
    for case_spec in model["dcf"]["cases"]:
        case_spec["fair_value_per_share"] = computed["result"]["cases"][case_spec["case"]]["fair_value_per_share"]
    verified = run_calculator({**model, "computed_by": "calculator"}, verify=True)
    assert verified["status"] == "ok"
    assert verified["result"]["verdict"] == "pass"
    assert verified["result"]["compared_cases"] >= 3


def test_verify_fails_on_corrupted_stored_value():
    model = _base_model()
    computed = run_calculator(model)
    for case_spec in model["dcf"]["cases"]:
        case_spec["fair_value_per_share"] = computed["result"]["cases"][case_spec["case"]]["fair_value_per_share"]
    model["dcf"]["cases"][1]["fair_value_per_share"] *= 1.5  # corrupt base case
    verified = run_calculator({**model, "computed_by": "calculator"}, verify=True)
    assert verified["result"]["verdict"] == "fail"
    assert any("base" in m for m in verified["result"]["mismatches"])


def test_verify_inconclusive_without_stored_values():
    verified = run_calculator({**_base_model(), "computed_by": "calculator"}, verify=True)
    assert verified["result"]["verdict"] == "inconclusive"
    assert verified["result"]["compared_cases"] == 0


def test_reproducibility_normalized_shape():
    """quant_report.reproducibility must be flat {verdict, mismatches, compared_cases}."""
    report = run_quant_analysis(_capex_spike_state())
    rep = report["quant_report"]["reproducibility"]
    assert rep["verdict"] == "pass"
    assert rep["compared_cases"] >= 3
    assert set(rep.keys()) == {"verdict", "mismatches", "compared_cases"}


# --- Fix 2: evaluate_valuation inherits state and reconciles -------------------------

def _workspace_state() -> dict:
    state = _capex_spike_state()
    return {
        "candidates": {
            "cand_test": {
                "candidate_id": "cand_test",
                "ticker": "TEST",
                "market_context": state["market_context"],
                "sec_financials": state["sec_financials"],
                "consensus_snapshot": {"status": "ok", "price_targets": {}, "eps_estimates": []},
                "diligence_dossier": {"expectation_gap": state["expectation_gap"]},
            }
        }
    }


def _valuation_tool():
    tools = create_agent_tools(cases_root=Path("cases"))
    return next(t for t in tools if t.name == "evaluate_valuation")


def test_evaluate_valuation_inherits_expectation_gap_and_macro(monkeypatch):
    def _offline_fred(series_ids):
        raise RuntimeError("offline test")

    monkeypatch.setattr("app.agent.tools._get_macro_context", _offline_fred)
    tool = _valuation_tool()
    raw = tool.func("TEST", "cand_test", injected_state=_workspace_state())
    result = json.loads(raw)
    assert result["status"] == "ok"
    assert result["provenance"]["assumption_source"] == "inherited_expectations"
    assert result["provenance"]["macro_source"] == "static_default"
    assert result["quant_report"]["assumptions"]["base_case_fcf_growth_rate"] == pytest.approx(0.16)
    assert result["valuation"]["reproducibility"] == "pass"


def test_evaluate_valuation_fetches_fred_when_state_lacks_macro(monkeypatch):
    captured = {}

    def fake_fred(series_ids):
        captured["series"] = series_ids
        return {"DGS10": {"latest_value": 4.1, "latest_date": "2026-09-25", "status": "ok"}}

    monkeypatch.setattr("app.agent.tools._get_macro_context", fake_fred)
    raw = _valuation_tool().func("TEST", "cand_test", injected_state=_workspace_state())
    result = json.loads(raw)
    assert result["provenance"]["macro_source"] == "fred_fetched"
    assert captured["series"] == ["DGS10"]
    assert result["quant_report"]["source_mapping"]["wacc_derivation"]["risk_free_rate"] == pytest.approx(0.041)


def test_evaluate_valuation_reconciles_with_diligence_valuation():
    first = json.loads(_valuation_tool().func("TEST", "cand_test", injected_state=_workspace_state()))
    computed_base = first["quant_report"]["valuation"]["fair_value_range"]["base"]

    state = _workspace_state()
    state["candidates"]["cand_test"]["diligence_dossier"]["valuation"] = {
        "fair_value_range": {"low": 1.0, "base": computed_base, "high": 999.0}
    }
    second = json.loads(_valuation_tool().func("TEST", "cand_test", injected_state=state))
    assert second["provenance"]["reconciliation"] == "matches_diligence"

    state["candidates"]["cand_test"]["diligence_dossier"]["valuation"] = {
        "fair_value_range": {"low": 1.0, "base": computed_base * 1.5, "high": 999.0}
    }
    third = json.loads(_valuation_tool().func("TEST", "cand_test", injected_state=state))
    assert third["provenance"]["reconciliation"] == "mismatch_vs_diligence"
