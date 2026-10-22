"""Unit tests for institutional SEC financials extraction.

Covers:
  - Working Capital (Accounts Payable, DPO, CCC)
  - Operating Lease Liabilities (ASC 842 / IFRS 16)
  - Interest Expense & Income Tax Provisions
  - True Unlevered Free Cash Flow (FCFF)
"""
from __future__ import annotations

import pytest

from app.sec.financials import SecFinancialsResult, get_sec_financials


def test_get_sec_financials_with_mocked_statements(monkeypatch):
    """get_sec_financials computes DPO, CCC, and unlevered FCFF from statements."""
    raw_mock = {
        "cik": "0000723125",
        "periods": ["Q1 2026", "Q4 2025"],
        "revenue": {"Q1 2026": 100_000_000.0, "Q4 2025": 90_000_000.0},
        "gross_profit": {"Q1 2026": 40_000_000.0, "Q4 2025": 36_000_000.0},
        "operating_income": {"Q1 2026": 20_000_000.0, "Q4 2025": 18_000_000.0},
        "net_income": {"Q1 2026": 15_000_000.0, "Q4 2025": 14_000_000.0},
        "cash_and_equivalents": {"Q1 2026": 30_000_000.0, "Q4 2025": 25_000_000.0},
        "total_debt": {"Q1 2026": 10_000_000.0, "Q4 2025": 10_000_000.0},
        "cash_from_operations": {"Q1 2026": 18_000_000.0, "Q4 2025": 16_000_000.0},
        "capex": {"Q1 2026": 5_000_000.0, "Q4 2025": 5_000_000.0},
        "inventory": {"Q1 2026": 30_000_000.0, "Q4 2025": 28_000_000.0},
        "accounts_receivable": {"Q1 2026": 20_000_000.0, "Q4 2025": 18_000_000.0},
        "accounts_payable": {"Q1 2026": 25_000_000.0, "Q4 2025": 22_000_000.0},
        "operating_lease_liabilities": {"Q1 2026": 8_000_000.0, "Q4 2025": 8_000_000.0},
        "interest_expense": {"Q1 2026": 1_000_000.0, "Q4 2025": 1_000_000.0},
        "income_tax_expense": {"Q1 2026": 4_000_000.0, "Q4 2025": 3_500_000.0},
        "total_assets": {"Q1 2026": 120_000_000.0, "Q4 2025": 115_000_000.0},
        "current_assets": {"Q1 2026": 50_000_000.0, "Q4 2025": 45_000_000.0},
        "current_liabilities": {"Q1 2026": 20_000_000.0, "Q4 2025": 18_000_000.0},
        "ppe": {"Q1 2026": 60_000_000.0, "Q4 2025": 58_000_000.0},
        "depreciation": {"Q1 2026": 3_000_000.0, "Q4 2025": 3_000_000.0},
        "sg_and_a": {"Q1 2026": 10_000_000.0, "Q4 2025": 9_000_000.0},
        "stock_based_compensation": {"Q1 2026": 2_000_000.0, "Q4 2025": 2_000_000.0},
        "preferred_stock": {"Q1 2026": 0.0, "Q4 2025": 0.0},
        "minority_interest": {"Q1 2026": 0.0, "Q4 2025": 0.0},
        "retained_earnings": {"Q1 2026": 40_000_000.0, "Q4 2025": 35_000_000.0},
        "stockholders_equity": {"Q1 2026": 90_000_000.0, "Q4 2025": 85_000_000.0},
        "customer_concentration": {},
    }

    from app.sec import financials
    monkeypatch.setattr(financials, "_fetch_xbrl_statements", lambda ticker, periods, as_of_date: raw_mock)

    sec = get_sec_financials("MOCK", as_of_date="2026-03-12")
    assert sec.status == "ok"

    # COGS = 100M - 40M = 60M
    # Days = 91.25
    # DIO = (30M / 60M) * 91.25 = 45.6 days
    # DSO = (20M / 100M) * 91.25 = 18.25 (18.3 days)
    # DPO = (25M / 60M) * 91.25 = 38.0 days
    # CCC = DIO + DSO - DPO = 45.6 + 18.25 - 38.0 = 25.9 days
    assert sec.dio["Q1 2026"] == pytest.approx(45.6, abs=0.1)
    assert sec.dso["Q1 2026"] == pytest.approx(18.2, abs=0.1)
    assert sec.dpo["Q1 2026"] == pytest.approx(38.0, abs=0.1)
    assert sec.ccc["Q1 2026"] == pytest.approx(25.9, abs=0.2)

    # FCF (CFO - CapEx) = 18M - 5M = 13.0M
    assert sec.fcf["Q1 2026"] == 13_000_000.0

    # Unlevered FCF (CFO - CapEx + Interest*(1-t))
    # Effective tax rate = 4M / 20M = 0.20
    # After-tax interest = 1M * (1 - 0.20) = 0.8M
    # Unlevered FCF = 13.0M + 0.8M = 13.8M
    assert sec.unlevered_fcf["Q1 2026"] == pytest.approx(13_800_000.0, rel=1e-3)
