"""Unit tests for institutional forensic accounting and ratio analytics.

Covers:
  - Altman Z-Score & Z''-Score (manufacturing & service/tech)
  - 5-stage DuPont ROE decomposition
  - ROIC vs WACC Economic Value Added (EVA) spread
  - Cash Conversion Cycle (CCC = DIO + DSO - DPO)
"""
from __future__ import annotations

import pytest

from app.market.forensics import (
    compute_altman_z_score,
    compute_dupont_analysis,
    compute_roic_economic_spread,
    evaluate_forensic_accounting,
)


def test_altman_z_score_manufacturing_profiles():
    """Altman 5-factor Z-Score identifies fortress balance sheet vs financial distress."""
    # Fortress profile: strong working capital, large retained earnings, robust EBIT
    safe_profile = compute_altman_z_score(
        working_capital=20_000_000.0,
        retained_earnings=30_000_000.0,
        ebit=15_000_000.0,
        market_cap=120_000_000.0,
        total_liabilities=30_000_000.0,
        sales=80_000_000.0,
        total_assets=100_000_000.0,
        is_manufacturing=True,
    )
    assert safe_profile is not None
    assert safe_profile["zone"] == "SAFE_ZONE"
    assert safe_profile["distress_risk"] == "LOW"
    assert safe_profile["z_score"] > 2.99

    # Distressed profile: negative working capital, negative retained earnings, operating losses
    distress_profile = compute_altman_z_score(
        working_capital=-15_000_000.0,
        retained_earnings=-20_000_000.0,
        ebit=-5_000_000.0,
        market_cap=10_000_000.0,
        total_liabilities=90_000_000.0,
        sales=30_000_000.0,
        total_assets=100_000_000.0,
        is_manufacturing=True,
    )
    assert distress_profile is not None
    assert distress_profile["zone"] == "DISTRESS_ZONE"
    assert distress_profile["distress_risk"] == "HIGH"
    assert distress_profile["z_score"] < 1.81


def test_altman_z_double_prime_service_tech():
    """Altman 4-factor Z''-Score validates non-manufacturing and software firms."""
    tech_safe = compute_altman_z_score(
        working_capital=40_000_000.0,
        retained_earnings=50_000_000.0,
        ebit=25_000_000.0,
        market_cap=200_000_000.0,
        total_liabilities=20_000_000.0,
        sales=100_000_000.0,
        total_assets=100_000_000.0,
        is_manufacturing=False,
    )
    assert tech_safe is not None
    assert tech_safe["model_variant"] == "service_tech_4_factor"
    assert tech_safe["zone"] == "SAFE_ZONE"
    assert tech_safe["z_score"] > 2.60


def test_dupont_5_stage_mathematical_identity():
    """5-stage DuPont terms multiply to equal Return on Equity."""
    net_inc = 18_000_000.0
    ebit = 25_000_000.0
    revenue = 100_000_000.0
    assets = 150_000_000.0
    equity = 80_000_000.0
    tax_exp = 5_000_000.0

    dupont = compute_dupont_analysis(
        net_income=net_inc,
        operating_income=ebit,
        revenue=revenue,
        total_assets=assets,
        stockholders_equity=equity,
        income_tax_expense=tax_exp,
    )
    assert dupont is not None
    # Product of: (Tax Burden) * (Interest Burden) * (Operating Margin) * (Asset Turnover) * (Financial Leverage)
    tax_burden = dupont["tax_burden"]
    interest_burden = dupont["interest_burden"]
    op_margin = dupont["operating_margin"]
    asset_turnover = dupont["asset_turnover"]
    leverage = dupont["financial_leverage"]

    reconstructed_roe = tax_burden * interest_burden * op_margin * asset_turnover * leverage
    expected_roe = net_inc / equity
    assert reconstructed_roe == pytest.approx(expected_roe, rel=1e-2)
    assert dupont["roe"] == pytest.approx(expected_roe, rel=1e-3)


def test_roic_economic_spread_value_creation():
    """ROIC minus WACC computes the economic value creation spread."""
    spread_res = compute_roic_economic_spread(
        operating_income=30_000_000.0,
        total_assets=150_000_000.0,
        cash_and_equivalents=20_000_000.0,
        current_liabilities=30_000_000.0,
        effective_tax_rate=0.20,
        wacc=0.09,
    )
    assert spread_res is not None
    # Invested Capital = 150M - 20M - 30M = 100M
    # NOPAT = 30M * 0.8 = 24M
    # ROIC = 24M / 100M = 24.0%
    # Spread = 24.0% - 9.0% = +15.0%
    assert spread_res["roic"] == pytest.approx(0.24, rel=1e-3)
    assert spread_res["economic_value_spread"] == pytest.approx(0.15, rel=1e-3)
    assert spread_res["value_creation_status"] == "VALUE_CREATING"


def test_forensic_audit_includes_institutional_metrics():
    """evaluate_forensic_accounting embeds Altman, DuPont, and Working Capital in its output."""
    mock_sec = {
        "periods": ["Q1 2026", "Q4 2025"],
        "revenue": {"Q1 2026": 100_000_000.0, "Q4 2025": 90_000_000.0},
        "gross_profit": {"Q1 2026": 40_000_000.0, "Q4 2025": 36_000_000.0},
        "gross_margin_pct": {"Q1 2026": 0.40, "Q4 2025": 0.40},
        "operating_income": {"Q1 2026": 20_000_000.0, "Q4 2025": 18_000_000.0},
        "net_income": {"Q1 2026": 15_000_000.0, "Q4 2025": 14_000_000.0},
        "cash_and_equivalents": {"Q1 2026": 30_000_000.0, "Q4 2025": 25_000_000.0},
        "total_debt": {"Q1 2026": 10_000_000.0, "Q4 2025": 10_000_000.0},
        "cash_from_operations": {"Q1 2026": 18_000_000.0, "Q4 2025": 16_000_000.0},
        "capex": {"Q1 2026": 5_000_000.0, "Q4 2025": 5_000_000.0},
        "total_assets": {"Q1 2026": 120_000_000.0, "Q4 2025": 115_000_000.0},
        "current_assets": {"Q1 2026": 50_000_000.0, "Q4 2025": 45_000_000.0},
        "current_liabilities": {"Q1 2026": 20_000_000.0, "Q4 2025": 18_000_000.0},
        "stockholders_equity": {"Q1 2026": 90_000_000.0, "Q4 2025": 85_000_000.0},
        "retained_earnings": {"Q1 2026": 40_000_000.0, "Q4 2025": 35_000_000.0},
        "stock_based_compensation": {"Q1 2026": 2_000_000.0, "Q4 2025": 2_000_000.0},
        "dio": {"Q1 2026": 45.0},
        "dso": {"Q1 2026": 38.0},
        "dpo": {"Q1 2026": 30.0},
        "ccc": {"Q1 2026": 53.0},
    }

    audit = evaluate_forensic_accounting(mock_sec)
    assert audit["status"] == "ok"
    assert "altman_z_score" in audit
    assert audit["altman_z_score"]["distress_risk"] == "LOW"
    assert "dupont_analysis" in audit
    assert "economic_value_spread" in audit
    assert "working_capital" in audit
    assert audit["working_capital"]["ccc"] == 53.0
