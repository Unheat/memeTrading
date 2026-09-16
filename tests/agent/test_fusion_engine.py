"""Focused tests for the fail-closed Institutional Fusion Engine."""
from app.agent.gate import evaluate_accounting_gate, evaluate_asymmetry_gate, evaluate_valuation_gate
from app.agent.specialists import run_forensic_analysis, run_quant_analysis
from app.agent.state import ResearchRequest, create_initial_state
from app.valuation.engine import run_calculator


def _model():
    """Build a valid deterministic calculator model."""
    return {"inputs": {"current_price": 10, "fcf_base": 100, "shares_diluted": 10}, "dcf": {"terminal_growth_rate": .025, "cases": [{"case": "low", "fcf_growth_rate": 0, "discount_rate": .12}, {"case": "base", "fcf_growth_rate": .03, "discount_rate": .10}, {"case": "high", "fcf_growth_rate": .08, "discount_rate": .09}]}}


def _source_backed_state():
    """Build state containing only mapped market and SEC financial inputs."""
    state = create_initial_state(ResearchRequest(query="x", ticker="X"), "case")
    state["market_context"] = {"quote": {"price": 10}, "fundamentals": {"shares_outstanding": 10}}
    state["sec_financials"] = {
        "status": "ok", "periods": ["2026-Q2"],
        "cash_from_operations": {"2026-Q2": 100}, "capex": {"2026-Q2": 20},
        "cash_and_equivalents": {"2026-Q2": 50}, "total_debt": {"2026-Q2": 10},
        "gross_margin_pct": {"2026-Q2": .3},
    }
    return state


def test_engine_calculates_reverse_dcf_and_scenarios():
    """Node boundary returns JSON results with required valuation outputs."""
    result = run_calculator(_model())
    assert result["status"] == "ok"
    assert result["result"]["reverse_dcf"]
    assert set(result["result"]["cases"]) == {"low", "base", "high"}


def test_quant_does_not_invent_missing_source_fields():
    """Quant reports unavailable rather than creating missing FCF or shares."""
    state = create_initial_state(ResearchRequest(query="x", ticker="X"), "case")
    state["market_context"] = {"quote": {"price": 10}, "fundamentals": {}}
    report = run_quant_analysis(state)["quant_report"]
    assert report["status"] == "unavailable"
    assert report["valuation"] is None


def test_sec_financials_feed_forensic_and_quant_source_mapping():
    """SEC CFO, CapEx, cash, and debt feed Phase 2/3 without market aliases."""
    state = _source_backed_state()
    forensic = run_forensic_analysis(state)["forensic_report"]
    quant = run_quant_analysis(state)["quant_report"]
    assert forensic["status"] == "available"
    assert forensic["forensic"]["gross_margin_pct"] == .3
    assert quant["status"] == "available"
    assert quant["model"]["inputs"] == {"current_price": 10.0, "fcf_base": 80.0, "shares_diluted": 10.0, "net_cash": 40.0}
    assert quant["source_mapping"]["fcf_base"] == "sec_financials.cash_from_operations[2026-Q2] - sec_financials.capex[2026-Q2]"
    assert quant["assumptions"] == quant["model"]["assumptions"]


def test_quant_requires_all_sec_fields_for_fcf_and_net_cash():
    """Quant never converts missing SEC periods into zero values."""
    state = _source_backed_state()
    del state["sec_financials"]["cash_from_operations"]
    report = run_quant_analysis(state)["quant_report"]
    assert report["status"] == "unavailable"
    assert "SEC cash from operations" in report["reason"]


def test_ordered_gates_fail_closed_when_reports_missing():
    """G2, G3, and G4 return validation status without fabricating outcomes."""
    assert not evaluate_accounting_gate({})["passed"]
    assert not evaluate_valuation_gate({})["passed"]
    assert not evaluate_asymmetry_gate({})["passed"]
