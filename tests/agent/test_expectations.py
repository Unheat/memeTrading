"""Tests for Michael Mauboussin reverse-expectations analysis and upgraded specialists."""
from __future__ import annotations

import json
from langchain_core.messages import AIMessage

from app.agent.expectations import run_expectations_analyst, _run_preliminary_reverse_dcf
from app.agent.specialists import (
    run_forensic_analysis,
    run_moat_analysis,
    run_quant_analysis,
    run_sector_analysis,
    run_thematic_analysis,
)
from app.agent.state import ResearchRequest, create_initial_state


class FakeExpectationsModel:
    """Mock valuation modeler returning structured JSON."""

    def invoke(self, messages):
        return AIMessage(content="""{
  "expectation_gap_verdict": "UNDERPRICED_CATALYST",
  "expectation_gap_summary": "Consensus underprices ground reality demand for HBM memory.",
  "implied_growth_interpretation": "Stock prices in 6% FCF growth, but actual demand warrants 16%.",
  "dcf_assumptions": {
    "terminal_growth_rate": 0.025,
    "projection_years": 5,
    "low_case": {"fcf_growth_rate": -0.04, "discount_rate": 0.11, "rationale": "Downturn"},
    "base_case": {"fcf_growth_rate": 0.09, "discount_rate": 0.095, "rationale": "Base ramp"},
    "high_case": {"fcf_growth_rate": 0.20, "discount_rate": 0.085, "rationale": "Hyperscaler backlog"}
  }
}""")


class FakeForensicModel:
    """Mock forensic accounting auditor returning structured JSON."""

    def invoke(self, messages):
        return AIMessage(content="""{
  "forensic_verdict": "CLEAN_INVESTMENT_GRADE",
  "beneish_m_score_risk": "CLEAN",
  "sloan_accrual_quality": "HIGH_QUALITY_CASH",
  "sbc_dilution_burden": "LOW",
  "leverage_solvency_risk": "LOW",
  "audit_summary": "High earnings quality with strong cash conversion."
}""")


class FakeSectorMoatModel:
    """Mock sector and moat specialist returning structured JSON."""

    def invoke(self, messages):
        prompt = str(getattr(messages[-1], "content", ""))
        if "economic moat" in prompt or "moat" in prompt:
            return AIMessage(content="""{
  "moat_rating": "WIDE",
  "durability_score": 9.0,
  "primary_moat_source": "SWITCHING_COSTS",
  "moat_summary": "Dominant ecosystem lock-in and high switching barriers."
}""")
        return AIMessage(content="""{
  "gross_margin_durability": "EXPANDING",
  "customer_concentration_risk": "MODERATE",
  "book_to_bill_visibility": "STRONG",
  "sector_thesis": "Favorable industry supply choke points."
}""")


def test_expectations_analyst_populates_expectation_gap_and_assumptions():
    """Verify run_expectations_analyst executes Mauboussin reverse expectations."""
    req = ResearchRequest(query="Analyze MU", ticker="MU", company="Micron")
    state = create_initial_state(req, case_id="case_mu")
    state["market_context"] = {
        "quote": {"price": 100.0},
        "fundamentals": {"shares_outstanding": 1_000_000_000.0},
        "volume_ratio_20d": {"value": 1.5},
    }
    state["consensus_snapshot"] = {
        "price_targets": {"mean": {"value": 140.0}},
        "eps_estimates": [{"metric": "eps", "growth": 0.15}],
        "revenue_estimates": [{"metric": "revenue", "growth": 0.12}],
    }
    state["sec_financials"] = {
        "status": "ok",
        "periods": ["2026-Q2"],
        "cash_from_operations": {"2026-Q2": 4_000_000_000.0},
        "capex": {"2026-Q2": 2_000_000_000.0},
        "cash_and_equivalents": {"2026-Q2": 9_000_000_000.0},
        "total_debt": {"2026-Q2": 5_000_000_000.0},
    }

    result = run_expectations_analyst(state, model=FakeExpectationsModel())

    assert "expectation_gap" in result
    gap = result["expectation_gap"]
    assert gap["verdict"] == "UNDERPRICED_CATALYST"
    assert "Consensus underprices" in gap["summary"]
    assert gap["terminal_growth_rate"] == 0.025
    assert gap["assumptions"]["base"]["growth"] == 0.09
    assert gap["assumptions"]["high"]["growth"] == 0.20


def test_preliminary_reverse_dcf_solves_implied_growth():
    """Verify solveReverseDCF computes implied growth rate via calculator.mjs."""
    res = _run_preliminary_reverse_dcf(
        price=100.0,
        shares=1_000_000_000.0,
        fcf=2_000_000_000.0,
        net_cash=4_000_000_000.0,
    )
    assert res is not None
    assert "implied_fcf_growth_rate" in res
    assert isinstance(res["implied_fcf_growth_rate"], float)


def test_quant_analysis_uses_dynamic_assumptions_from_expectation_gap():
    """Verify run_quant_analysis uses dynamic DCF assumptions authored by expectations analyst."""
    req = ResearchRequest(query="Analyze MU", ticker="MU", company="Micron")
    state = create_initial_state(req, case_id="case_mu")
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
    state["expectation_gap"] = {
        "verdict": "UNDERPRICED_CATALYST",
        "terminal_growth_rate": 0.028,
        "projection_years": 5,
        "assumptions": {
            "low": {"growth": -0.02, "discount": 0.11},
            "base": {"growth": 0.12, "discount": 0.09},
            "high": {"growth": 0.22, "discount": 0.08},
        },
    }

    report = run_quant_analysis(state)
    assert report["quant_report"]["status"] == "available"
    assert report["quant_report"]["assumptions"]["base_case_fcf_growth_rate"] == 0.12
    assert report["quant_report"]["assumptions"]["terminal_growth_rate"] == 0.028


def test_forensic_accounting_auditor_model_evaluation():
    """Verify run_forensic_analysis runs LLM forensic accounting audit."""
    req = ResearchRequest(query="Analyze MU", ticker="MU", company="Micron")
    state = create_initial_state(req, case_id="case_mu")
    state["sec_financials"] = {
        "status": "ok",
        "periods": ["2026-Q2"],
        "gross_margin_pct": {"2026-Q2": 0.36},
        "operating_margin_pct": {"2026-Q2": 0.22},
        "inventory_qoq_change_pct": {"2026-Q2": -0.05},
        "net_income": {"2026-Q2": 1_800_000_000.0},
        "cash_from_operations": {"2026-Q2": 2_500_000_000.0},
        "capex": {"2026-Q2": 1_200_000_000.0},
    }
    res = run_forensic_analysis(state, model=FakeForensicModel())
    assert res["forensic_report"]["status"] == "available"
    assert res["forensic_report"]["verdict"] == "CLEAN_INVESTMENT_GRADE"
    assert res["forensic_report"]["audit"]["beneish_m_score_risk"] == "CLEAN"


def test_sector_and_moat_specialist_model_evaluations():
    """Verify run_sector_analysis and run_moat_analysis run LLM specialist audits."""
    req = ResearchRequest(query="Analyze MU", ticker="MU", company="Micron")
    state = create_initial_state(req, case_id="case_mu")
    state["evidence"] = [{"quote": "Customer backlog locked for 2 years", "source_url": "https://sec.gov"}]

    model = FakeSectorMoatModel()
    sector_res = run_sector_analysis(state, model=model)
    moat_res = run_moat_analysis(state, model=model)

    assert sector_res["sector_report"]["status"] == "available"
    assert sector_res["sector_report"]["analysis"]["gross_margin_durability"] == "EXPANDING"

    assert moat_res["moat_report"]["status"] == "available"
    assert moat_res["moat_report"]["analysis"]["moat_rating"] == "WIDE"
    assert moat_res["moat_report"]["analysis"]["durability_score"] == 9.0
