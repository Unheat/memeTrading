"""Unit tests for deterministic forensic accounting calculations."""
from __future__ import annotations

import pytest

from app.market.forensics import (
    compute_beneish_m_score,
    compute_sloan_accrual,
    compute_sbc_dilution,
    compute_leverage_profile,
    evaluate_forensic_accounting,
)


def test_beneish_m_score_clean():
    """Verify standard baseline parameters produce clean M-Score."""
    res = compute_beneish_m_score()
    assert res["is_manipulator_probability_high"] is False
    assert res["verdict"] == "CLEAN_LOW_MANIPULATION_RISK"
    assert res["threshold"] == -1.78
    assert res["m_score"] < -1.78


def test_beneish_m_score_manipulator():
    """Verify aggressive accruals and revenue inflation trigger manipulator alert."""
    res = compute_beneish_m_score(
        dsri=2.5,
        sgi=2.0,
        tata=0.35,
        gmi=1.8,
    )
    assert res["is_manipulator_probability_high"] is True
    assert res["verdict"] == "HIGH_RISK_EARNINGS_MANIPULATION"
    assert res["m_score"] > -1.78


def test_sloan_accrual_quality_bands():
    """Verify Sloan Accruals identify aggressive vs conservative cash conversion."""
    # Aggressive accruals: Net Income ($5B) >> CFO ($1B) on $20B assets -> ratio = 0.20
    bad = compute_sloan_accrual(net_income=5_000.0, cfo=1_000.0, total_assets=20_000.0)
    assert bad is not None
    assert bad["accrual_ratio"] == 0.2
    assert "Aggressive Accruals" in bad["quality_band"]

    # Conservative conversion: Net Income ($1B) << CFO ($5B) on $20B assets -> ratio = -0.20
    good = compute_sloan_accrual(net_income=1_000.0, cfo=5_000.0, total_assets=20_000.0)
    assert good is not None
    assert good["accrual_ratio"] == -0.2
    assert "Conservative" in good["quality_band"]

    # Normal band: Net Income ($2B), CFO ($2.2B) on $20B assets
    normal = compute_sloan_accrual(net_income=2_000.0, cfo=2_200.0, total_assets=20_000.0)
    assert normal is not None
    assert normal["quality_band"] == "NORMAL_EARNINGS_QUALITY"


def test_sbc_dilution_tiers():
    """Verify SBC burden flags high dilution relative to Free Cash Flow."""
    # Low dilution: $100M SBC on $1B FCF (10%)
    low = compute_sbc_dilution(sbc_expense=100.0, fcf=1_000.0)
    assert low is not None
    assert low["burden_level"] == "LOW"
    assert low["sbc_as_pct_of_fcf"] == 10.0

    # High dilution: $400M SBC on $1B FCF (40%)
    high = compute_sbc_dilution(sbc_expense=400.0, fcf=1_000.0)
    assert high is not None
    assert high["burden_level"] == "HIGH_DILUTION_BURDEN"
    assert high["sbc_as_pct_of_fcf"] == 40.0


def test_leverage_profile():
    """Verify net cash and excessive debt detection."""
    # Net cash fortress
    cash_heavy = compute_leverage_profile(total_debt=5_000.0, cash_and_equivalents=15_000.0, operating_income=4_000.0)
    assert cash_heavy["is_net_cash_positive"] is True
    assert cash_heavy["leverage_risk"] == "LOW_OR_NET_CASH"

    # Excessive debt: $25B debt, $1B cash ($24B net debt) on $4B EBIT = 6.0x
    high_debt = compute_leverage_profile(total_debt=25_000.0, cash_and_equivalents=1_000.0, operating_income=4_000.0)
    assert high_debt["is_net_cash_positive"] is False
    assert high_debt["net_debt_to_operating_income"] == 6.0
    assert high_debt["leverage_risk"] == "EXCESSIVE_LEVERAGE"


def test_evaluate_forensic_accounting_end_to_end():
    """Verify evaluate_forensic_accounting runs deterministically on sec_financials."""
    sec = {
        "status": "ok",
        "periods": ["2026-Q2", "2025-Q2"],
        "revenue": {"2026-Q2": 60_000.0, "2025-Q2": 50_000.0},
        "gross_margin_pct": {"2026-Q2": 0.68, "2025-Q2": 0.69},
        "net_income": {"2026-Q2": 20_000.0, "2025-Q2": 16_000.0},
        "cash_from_operations": {"2026-Q2": 24_000.0, "2025-Q2": 19_000.0},
        "capex": {"2026-Q2": 4_000.0, "2025-Q2": 3_000.0},
        "total_assets": {"2026-Q2": 150_000.0, "2025-Q2": 130_000.0},
        "total_debt": {"2026-Q2": 40_000.0, "2025-Q2": 40_000.0},
        "cash_and_equivalents": {"2026-Q2": 80_000.0, "2025-Q2": 70_000.0},
        "stock_based_compensation": {"2026-Q2": 2_000.0, "2025-Q2": 1_800.0},
        "operating_income": {"2026-Q2": 25_000.0, "2025-Q2": 21_000.0},
    }

    report = evaluate_forensic_accounting(sec)
    assert report["status"] == "ok"
    assert report["verdict"] == "QUALIFIED_NORMALIZED_ADJUSTMENT"
    assert report["beneish_m_score"]["is_manipulator_probability_high"] is False
    assert report["sloan_accruals"]["quality_band"] == "NORMAL_EARNINGS_QUALITY"
    assert report["leverage"]["is_net_cash_positive"] is True
    assert len(report["red_flags"]) == 0


def test_evaluate_forensic_accounting_computes_all_beneish_indices():
    """Verify all 8 Beneish indices compute dynamically when full SEC balance sheet concepts are present."""
    sec = {
        "status": "ok",
        "periods": ["2026-Q2", "2025-Q2"],
        "revenue": {"2026-Q2": 100.0, "2025-Q2": 80.0},
        "gross_margin_pct": {"2026-Q2": 0.50, "2025-Q2": 0.40},
        "operating_income": {"2026-Q2": 30.0, "2025-Q2": 20.0},
        "net_income": {"2026-Q2": 25.0, "2025-Q2": 15.0},
        "cash_from_operations": {"2026-Q2": 35.0, "2025-Q2": 25.0},
        "capex": {"2026-Q2": 10.0, "2025-Q2": 8.0},
        "total_assets": {"2026-Q2": 200.0, "2025-Q2": 160.0},
        "accounts_receivable": {"2026-Q2": 20.0, "2025-Q2": 12.0},
        "current_assets": {"2026-Q2": 80.0, "2025-Q2": 60.0},
        "ppe": {"2026-Q2": 70.0, "2025-Q2": 60.0},
        "depreciation": {"2026-Q2": 7.0, "2025-Q2": 6.0},
        "sg_and_a": {"2026-Q2": 15.0, "2025-Q2": 10.0},
        "current_liabilities": {"2026-Q2": 30.0, "2025-Q2": 25.0},
        "total_debt": {"2026-Q2": 40.0, "2025-Q2": 35.0},
        "cash_and_equivalents": {"2026-Q2": 50.0, "2025-Q2": 40.0},
        "stock_based_compensation": {"2026-Q2": 5.0, "2025-Q2": 4.0},
    }

    report = evaluate_forensic_accounting(sec)
    indices = report["beneish_m_score"]["indices"]
    # SGI: 100 / 80 = 1.25
    assert indices["sgi"] == pytest.approx(1.25, abs=1e-2)
    # GMI: 0.40 / 0.50 = 0.8
    assert indices["gmi"] == pytest.approx(0.8, abs=1e-2)
    # DSRI: (20/100) / (12/80) = 0.20 / 0.15 = 1.333
    assert indices["dsri"] == pytest.approx(1.333, abs=1e-2)
    # SGAI: (15/100) / (10/80) = 0.15 / 0.125 = 1.2
    assert indices["sgai"] == pytest.approx(1.2, abs=1e-2)
    # TATA: (30 - 35) / 200 = -5 / 200 = -0.025
    assert indices["tata"] == pytest.approx(-0.025, abs=1e-2)
    # Verify non-trivial AQI and LVGI
    assert indices["aqi"] is not None
    assert indices["lvgi"] is not None
    assert indices["depi"] is not None
