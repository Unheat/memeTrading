"""Tests for SEC ASC 280-10-50-42 customer concentration footnote extraction and red-team integration."""
from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest
from app.sec.financials import _extract_customer_concentration, SecFinancialsResult
from app.agent.adversarial import run_adversarial_red_team


def test_extract_customer_concentration_above_threshold():
    """Verify customer concentration >= 10% is flagged with accurate percentages."""
    mock_company = MagicMock()
    mock_company.facts = [
        SimpleNamespace(
            concept="ConcentrationRiskPercentage1",
            value=0.17,
            dimensions="CustomerAMember",
            period_end="2025-08-31",
            filing_date="2025-10-01",
        ),
        SimpleNamespace(
            concept="ConcentrationRiskPercentage1",
            value=0.12,
            dimensions="CustomerBMember",
            period_end="2025-08-31",
            filing_date="2025-10-01",
        ),
        SimpleNamespace(
            concept="MajorCustomersRevenuePercentage",
            value=0.05,
            dimensions="CustomerCMember",
            period_end="2025-08-31",
            filing_date="2025-10-01",
        ),
    ]

    result = _extract_customer_concentration(mock_company)
    assert result["has_concentration_risk"] is True
    assert result["top_customer_pct"] == 17.0
    assert len(result["major_customers"]) == 2
    assert result["aggregate_major_pct"] == 29.0
    assert result["major_customers"][0]["customer"] == "CustomerA"
    assert result["major_customers"][0]["pct"] == 17.0
    assert result["major_customers"][1]["customer"] == "CustomerB"
    assert result["major_customers"][1]["pct"] == 12.0


def test_extract_customer_concentration_below_threshold():
    """Verify that issuers with diversified revenue (< 10% per customer) are marked clean."""
    mock_company = MagicMock()
    mock_company.facts = [
        SimpleNamespace(
            concept="ConcentrationRiskPercentage1",
            value=0.08,
            dimensions="CustomerAMember",
            period_end="2025-08-31",
            filing_date="2025-10-01",
        ),
        SimpleNamespace(
            concept="ConcentrationRiskPercentage1",
            value=0.06,
            dimensions="CustomerBMember",
            period_end="2025-08-31",
            filing_date="2025-10-01",
        ),
    ]

    result = _extract_customer_concentration(mock_company)
    assert result["has_concentration_risk"] is False
    assert result["top_customer_pct"] is None
    assert result["major_customers"] == []
    assert result["aggregate_major_pct"] is None


def test_extract_customer_concentration_pit_filtering():
    """Verify facts filed after the as_of_date are excluded for point-in-time integrity."""
    mock_company = MagicMock()
    mock_company.facts = [
        # Older filing (before PIT cutoff)
        SimpleNamespace(
            concept="ConcentrationRiskPercentage1",
            value=0.14,
            dimensions="CustomerAMember",
            period_end="2025-08-31",
            filing_date="2025-10-01",
        ),
        # Future filing (after PIT cutoff)
        SimpleNamespace(
            concept="ConcentrationRiskPercentage1",
            value=0.25,
            dimensions="HyperscalerXMember",
            period_end="2026-08-31",
            filing_date="2026-10-01",
        ),
    ]

    # As of 2026-01-01, only the 2025 filing should be visible
    result = _extract_customer_concentration(mock_company, as_of_date="2026-01-01")
    assert result["has_concentration_risk"] is True
    assert result["top_customer_pct"] == 14.0
    assert len(result["major_customers"]) == 1
    assert result["major_customers"][0]["customer"] == "CustomerA"


def test_adversarial_red_team_mandate_injection():
    """Verify Red Team system injects mandatory customer concentration objection when risk is present."""
    mock_model = MagicMock()
    mock_response = MagicMock()
    mock_response.content = """{
        "falsifiable_objections": ["Hyperscaler pricing squeeze", "Dual-sourcing risk", "CapEx digestion", "Supply glut"],
        "numeric_kill_criteria": ["Top customer share drops > 500 bps", "Gross margin drops below 35%"],
        "bear_floor_price": 180.0,
        "bear_thesis_summary": "Concentrated customer base exposes company to margin erosion."
    }"""
    mock_model.invoke.return_value = mock_response

    state = {
        "ticker": "MU",
        "company": "Micron Technology",
        "sec_financials": {
            "status": "ok",
            "customer_concentration": {
                "has_concentration_risk": True,
                "top_customer_pct": 17.0,
                "major_customers": [{"customer": "Customer A", "pct": 17.0}],
                "aggregate_major_pct": 17.0,
            },
        },
    }

    res = run_adversarial_red_team(state, mock_model)
    report = res["adversarial_report"]
    assert report.status == "available"
    assert len(report.falsifiable_objections) == 4

    # Verify that the invoked prompt contained the mandatory mandate
    invoked_messages = mock_model.invoke.call_args[0][0]
    human_msg = invoked_messages[1].content
    assert "CRITICAL RED-TEAM MANDATE (ASC 280-10-50-42 Customer Concentration)" in human_msg
    assert "17.0%" in human_msg
