"""Unit tests for Altman Z-Score with public market capitalization."""
from __future__ import annotations

import pytest

from app.market.forensics import compute_altman_z_score, evaluate_forensic_accounting


def test_altman_z_score_uses_market_cap_for_x4():
    """Factor X4 uses market_cap / total_liabilities for public manufacturing companies."""
    # A public tech/manufacturing company with high market cap ($100B) but low book equity ($5B)
    # Total Assets: $50B, Total Liabilities: $45B, Book Equity: $5B
    # Working Capital: $10B, Retained Earnings: $5B, EBIT: $10B, Sales: $40B
    total_assets = 50_000_000_000.0
    tot_liab = 45_000_000_000.0
    market_cap = 100_000_000_000.0

    # With market_cap provided:
    z_with_mc = compute_altman_z_score(
        working_capital=10_000_000_000.0,
        retained_earnings=5_000_000_000.0,
        ebit=10_000_000_000.0,
        market_cap=market_cap,
        total_liabilities=tot_liab,
        sales=40_000_000_000.0,
        total_assets=total_assets,
        is_manufacturing=True,
    )

    # Without market_cap (falls back to book equity):
    z_without_mc = compute_altman_z_score(
        working_capital=10_000_000_000.0,
        retained_earnings=5_000_000_000.0,
        ebit=10_000_000_000.0,
        market_cap=None,
        total_liabilities=tot_liab,
        sales=40_000_000_000.0,
        total_assets=total_assets,
        is_manufacturing=True,
    )

    assert z_with_mc is not None
    assert z_without_mc is not None

    # X4 with market cap: 100B / 45B = 2.22; with book equity: 5B / 45B = 0.11
    # 0.6 * (2.22 - 0.11) = ~1.26 difference in Z-Score!
    assert z_with_mc["z_score"] > z_without_mc["z_score"]
    assert z_with_mc["zone"] == "SAFE_ZONE"


def test_evaluate_forensic_accounting_resolves_market_cap_from_context():
    """evaluate_forensic_accounting resolves market_cap from market_context."""
    sec = {
        "periods": ["2024-Q3", "2023-Q3"],
        "total_assets": {"2024-Q3": 50_000_000_000.0, "2023-Q3": 45_000_000_000.0},
        "stockholders_equity": {"2024-Q3": 5_000_000_000.0, "2023-Q3": 5_000_000_000.0},
        "current_assets": {"2024-Q3": 20_000_000_000.0, "2023-Q3": 18_000_000_000.0},
        "current_liabilities": {"2024-Q3": 10_000_000_000.0, "2023-Q3": 9_000_000_000.0},
        "operating_income": {"2024-Q3": 8_000_000_000.0, "2023-Q3": 7_000_000_000.0},
        "revenue": {"2024-Q3": 30_000_000_000.0, "2023-Q3": 25_000_000_000.0},
        "retained_earnings": {"2024-Q3": 4_000_000_000.0, "2023-Q3": 3_500_000_000.0},
        "cash_from_operations": {"2024-Q3": 9_000_000_000.0, "2023-Q3": 8_000_000_000.0},
        "capex": {"2024-Q3": 2_000_000_000.0, "2023-Q3": 1_800_000_000.0},
    }
    market_context = {
        "fundamentals": {"market_cap": {"value": 150_000_000_000.0, "reliable": True}}
    }

    audit_with_ctx = evaluate_forensic_accounting(sec, market_context=market_context)
    audit_without_ctx = evaluate_forensic_accounting(sec)

    z_ctx = audit_with_ctx["altman_z_score"]
    z_no_ctx = audit_without_ctx["altman_z_score"]

    assert z_ctx is not None and z_no_ctx is not None
    assert z_ctx["z_score"] > z_no_ctx["z_score"]
    assert z_ctx["zone"] == "SAFE_ZONE"
