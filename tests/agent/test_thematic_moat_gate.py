"""Tests for micro-to-macro economic moat gating in run_thematic_analysis."""
from unittest.mock import MagicMock
import pytest
from app.agent.specialists import run_thematic_analysis


def test_low_gross_margin_triggers_commoditized_capex_trap():
    """Verify that a candidate with < 35% gross margin and no strong moat is flagged as COMMODITIZED_CAPEX_TRAP."""
    mock_model = MagicMock()
    mock_response = MagicMock()
    mock_response.content = """{
        "thematic_summary": "Beneficiary of secular global AI datacenter buildout wave.",
        "secular_capex_wave_phase": "Phase 2 Infrastructure Ramp",
        "bottleneck_monopoly_score": 9,
        "thematic_tailwinds": "STRONG_SECULAR"
    }"""
    mock_model.invoke.return_value = mock_response

    state = {
        "ticker": "COMM",
        "company": "Commodity Server Assembler",
        "evidence": [
            {"quote": "Company supplies rack assemblies to hyperscalers.", "source_url": "https://sec.gov/10k"},
        ],
        "sec_financials": {
            "status": "ok",
            "periods": ["2026-Q1"],
            "gross_margin_pct": {"2026-Q1": 0.185},  # 18.5% < 35%
        },
        "moat_report": {
            "status": "available",
            "analysis": {"moat_rating": "None"},
        },
    }

    res = run_thematic_analysis(state, mock_model)
    report = res["thematic_report"]
    analysis = report["analysis"]

    assert analysis["thematic_tailwinds"] == "COMMODITIZED_CAPEX_TRAP"
    assert analysis["bottleneck_monopoly_score"] <= 3
    assert "COMMODITIZED_CAPEX_TRAP" in analysis["micro_gating_warning"]
    assert "COMMODITIZED_CAPEX_TRAP" in report["thesis"]


def test_high_gross_margin_passes_micro_gate():
    """Verify that candidates with pristine gross margins (> 35%) retain high secular bottleneck ratings."""
    mock_model = MagicMock()
    mock_response = MagicMock()
    mock_response.content = """{
        "thematic_summary": "Crucial silicon bottleneck with pricing power.",
        "secular_capex_wave_phase": "Phase 2 Infrastructure Ramp",
        "bottleneck_monopoly_score": 9,
        "thematic_tailwinds": "STRONG_SECULAR"
    }"""
    mock_model.invoke.return_value = mock_response

    state = {
        "ticker": "MU",
        "company": "Micron Technology",
        "evidence": [
            {"quote": "Micron HBM3E sold out through 2026.", "source_url": "https://sec.gov/10q"},
        ],
        "sec_financials": {
            "status": "ok",
            "periods": ["2026-Q1"],
            "gross_margin_pct": {"2026-Q1": 0.5604},  # 56.04% > 35%
        },
        "moat_report": {
            "status": "available",
            "analysis": {"moat_rating": "Narrow Moat"},
        },
    }

    res = run_thematic_analysis(state, mock_model)
    report = res["thematic_report"]
    analysis = report["analysis"]

    assert analysis["thematic_tailwinds"] == "STRONG_SECULAR"
    assert analysis["bottleneck_monopoly_score"] == 9
    assert "micro_gating_warning" not in analysis
