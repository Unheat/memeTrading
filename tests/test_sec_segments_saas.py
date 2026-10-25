"""Unit tests for SEC segment reporting and subscription/SaaS unit economics."""
from __future__ import annotations

from unittest.mock import MagicMock
import pytest

from app.sec.financials import (
    SecFinancialsResult,
    _extract_saas_metrics,
    _extract_segment_reporting,
)


def _make_mock_fact(
    concept: str,
    value: float,
    member: str | None = None,
    axis: str | None = None,
    fiscal_year: int = 2024,
    fiscal_period: str = "Q3",
    period_end: str = "2024-09-30",
    filing_date: str = "2024-10-25",
) -> MagicMock:
    f = MagicMock()
    f.concept = concept
    f.value = value
    f.member = member
    f.axis = axis
    f.fiscal_year = fiscal_year
    f.fiscal_period = fiscal_period
    f.period_end = period_end
    f.filing_date = filing_date
    dims = {}
    if axis and member:
        dims[axis] = member
    f.dimensions = dims
    return f


def test_extract_segment_reporting_dimensional():
    """Extract segment revenue and operating profit across StatementBusinessSegmentsAxis."""
    company = MagicMock()
    company.facts = [
        _make_mock_fact(
            concept="us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
            value=35_000_000_000.0,
            member="us-gaap:AWSMember",
            axis="srt:StatementBusinessSegmentsAxis",
        ),
        _make_mock_fact(
            concept="us-gaap:OperatingIncomeLoss",
            value=10_500_000_000.0,
            member="us-gaap:AWSMember",
            axis="srt:StatementBusinessSegmentsAxis",
        ),
        _make_mock_fact(
            concept="us-gaap:Revenues",
            value=95_000_000_000.0,
            member="us-gaap:NorthAmericaMember",
            axis="srt:StatementBusinessSegmentsAxis",
        ),
        _make_mock_fact(
            concept="us-gaap:OperatingIncomeLoss",
            value=5_700_000_000.0,
            member="us-gaap:NorthAmericaMember",
            axis="srt:StatementBusinessSegmentsAxis",
        ),
        # Consolidated total row - should be filtered out
        _make_mock_fact(
            concept="us-gaap:Revenues",
            value=130_000_000_000.0,
            member="us-gaap:TotalMember",
            axis="srt:StatementBusinessSegmentsAxis",
        ),
    ]

    segments = _extract_segment_reporting(company, ["2024-Q3"])
    assert len(segments) == 2

    aws = next(s for s in segments if s["name"] == "AWS")
    assert aws["revenue"] == 35_000_000_000.0
    assert aws["operating_income"] == 10_500_000_000.0
    assert aws["operating_margin_pct"] == 30.0

    na = next(s for s in segments if s["name"] == "North America")
    assert na["revenue"] == 95_000_000_000.0
    assert na["operating_income"] == 5_700_000_000.0
    assert na["operating_margin_pct"] == 6.0


def test_extract_saas_metrics_and_rule_of_40():
    """Extract RPO, cRPO, ARR, NRR, and compute Rule of 40 deterministically."""
    company = MagicMock()
    company.facts = [
        _make_mock_fact(concept="us-gaap:RevenueRemainingPerformanceObligation", value=25_000_000_000.0),
        _make_mock_fact(concept="crm:CurrentRemainingPerformanceObligation", value=13_000_000_000.0),
        _make_mock_fact(concept="crm:AnnualRecurringRevenue", value=12_000_000_000.0),
        _make_mock_fact(concept="crm:DollarBasedNetRetention", value=1.14),  # 114% NRR
    ]

    periods = ["2024-Q3", "2024-Q2", "2024-Q1", "2023-Q4", "2023-Q3"]
    revenue_series = {
        "2024-Q3": 10_000_000_000.0,
        "2023-Q3": 8_000_000_000.0,  # 25% YoY growth
    }
    fcf_series = {
        "2024-Q3": 2_500_000_000.0,  # 25% FCF margin
    }
    opm_series = {
        "2024-Q3": 20.0,  # 20% Op margin
    }

    metrics = _extract_saas_metrics(
        company,
        periods,
        as_of_date="2026-10-25",
        revenue_series=revenue_series,
        fcf_series=fcf_series,
        op_margin_series=opm_series,
    )

    assert metrics["is_subscription_model"] is True
    assert metrics["remaining_performance_obligation"] == 25_000_000_000.0
    assert metrics["current_remaining_performance_obligation"] == 13_000_000_000.0
    assert metrics["crpo_pct_of_total_rpo"] == 52.0
    assert metrics["annual_recurring_revenue"] == 12_000_000_000.0
    assert metrics["net_retention_rate_pct"] == 114.0

    # YoY Growth: (10B - 8B) / 8B = 25.0%
    # FCF Margin: 2.5B / 10B = 25.0%
    # Rule of 40 (FCF): 25.0% + 25.0% = 50.0% -> OUTPERFORM
    assert metrics["rule_of_40_fcf_pct"] == 50.0
    assert metrics["rule_of_40_status"] == "OUTPERFORM"
    # Rule of 40 (Op): 25.0% + 20.0% = 45.0%
    assert metrics["rule_of_40_op_pct"] == 45.0


def test_sec_financials_result_segments_saas_serialization():
    """SecFinancialsResult preserves segments and saas_metrics through to_dict and from_dict."""
    result = SecFinancialsResult(
        ticker="NOW",
        status="ok",
        periods=("2024-Q3", "2024-Q2"),
        revenue={"2024-Q3": 2_500_000_000.0},
        gross_profit={"2024-Q3": 2_000_000_000.0},
        gross_margin_pct={"2024-Q3": 80.0},
        operating_income={"2024-Q3": 500_000_000.0},
        operating_margin_pct={"2024-Q3": 20.0},
        net_income={"2024-Q3": 400_000_000.0},
        cash_and_equivalents={"2024-Q3": 3_000_000_000.0},
        total_debt={"2024-Q3": 1_000_000_000.0},
        net_cash={"2024-Q3": 2_000_000_000.0},
        inventory={},
        inventory_qoq_change_pct={},
        cash_from_operations={"2024-Q3": 700_000_000.0},
        capex={"2024-Q3": 100_000_000.0},
        provider="sec_xbrl",
        as_of="2026-10-25",
        segments=[
            {"name": "Subscription", "revenue": 2_400_000_000.0, "operating_income": 600_000_000.0, "operating_margin_pct": 25.0},
            {"name": "Professional Services", "revenue": 100_000_000.0, "operating_income": -100_000_000.0, "operating_margin_pct": -100.0},
        ],
        saas_metrics={
            "is_subscription_model": True,
            "remaining_performance_obligation": 15_000_000_000.0,
            "rule_of_40_fcf_pct": 48.0,
            "rule_of_40_status": "OUTPERFORM",
        },
    )

    d = result.to_dict()
    assert len(d["segments"]) == 2
    assert d["saas_metrics"]["rule_of_40_status"] == "OUTPERFORM"

    restored = SecFinancialsResult.from_dict(d)
    assert len(restored.segments) == 2
    assert restored.segments[0]["name"] == "Subscription"
    assert restored.saas_metrics["rule_of_40_fcf_pct"] == 48.0
