"""Institutional valuation engine unit tests.

Covers:
  - Mid-year discounting convention vs year-end discounting
  - Enterprise Value to Equity Value bridge with operating leases, preferred stock, minority interest
  - Michael Mauboussin Expectations Reverse DCF (revenue and NOPAT inversion, negative FCF resilience)
"""
from __future__ import annotations

import pytest

from app.valuation.engine import run_calculator


def test_mid_year_discounting_vs_year_end():
    """Mid-year discounting reflects continuous cash flow generation and exceeds year-end PV."""
    base_model = {
        "inputs": {
            "current_price": 100.0,
            "fcf_base": 1_000_000_000.0,
            "shares_diluted": 100_000_000,
            "net_cash": 0.0,
        },
        "dcf": {
            "terminal_growth_rate": 0.025,
            "projection_years": 5,
            "cases": [
                {"case": "base", "fcf_growth_rate": 0.10, "discount_rate": 0.095},
            ],
        },
    }

    # Run with default mid-year discounting
    mid_year_res = run_calculator(base_model)
    assert mid_year_res["status"] == "ok"
    mid_year_pv_flows = mid_year_res["result"]["cases"]["base"]["pv_explicit_flows"]

    # Run with explicit year-end discounting
    year_end_model = {
        **base_model,
        "inputs": {
            **base_model["inputs"],
            "discounting_convention": "year_end",
        },
    }
    year_end_res = run_calculator(year_end_model)
    assert year_end_res["status"] == "ok"
    year_end_pv_flows = year_end_res["result"]["cases"]["base"]["pv_explicit_flows"]

    # Mid-year PV must strictly exceed year-end PV by roughly (1 + r)^0.5 ≈ 4.6%
    assert mid_year_pv_flows > year_end_pv_flows
    ratio = mid_year_pv_flows / year_end_pv_flows
    assert ratio == pytest.approx((1.0 + 0.095) ** 0.5, rel=1e-2)


def test_ev_to_equity_bridge_senior_claims():
    """Operating lease liabilities, preferred stock, and minority interest deduct from equity value."""
    model_without_claims = {
        "inputs": {
            "current_price": 50.0,
            "fcf_base": 500_000_000.0,
            "shares_diluted": 50_000_000,
            "net_cash": 100_000_000.0,
        },
        "dcf": {
            "terminal_growth_rate": 0.025,
            "projection_years": 5,
            "cases": [{"case": "base", "fcf_growth_rate": 0.05, "discount_rate": 0.09}],
        },
    }
    res_clean = run_calculator(model_without_claims)
    eq_val_clean = res_clean["result"]["cases"]["base"]["equity_value"]

    # Add $200M operating leases and $50M preferred stock
    model_with_claims = {
        **model_without_claims,
        "inputs": {
            **model_without_claims["inputs"],
            "operating_leases": 200_000_000.0,
            "preferred_stock": 50_000_000.0,
        },
    }
    res_claims = run_calculator(model_with_claims)
    eq_val_claims = res_claims["result"]["cases"]["base"]["equity_value"]

    # Equity value must decrease by exactly 250M
    assert eq_val_clean - eq_val_claims == pytest.approx(250_000_000.0, rel=1e-3)
    assert res_claims["result"]["cases"]["base"]["fair_value_per_share"] < res_clean["result"]["cases"]["base"]["fair_value_per_share"]


def test_mauboussin_expectations_reverse_dcf_negative_fcf_resilience():
    """Mauboussin Expectations Reverse DCF resolves market-implied growth even when trailing FCF is negative."""
    model_cyclical_trough = {
        "inputs": {
            "current_price": 40.0,
            "shares_diluted": 1_000_000_000,
            "fcf_base": -500_000_000.0,  # Negative FCF (e.g. cycle trough / CapEx ramp)
            "net_cash": 2_000_000_000.0,
            "revenue": 30_000_000_000.0,
            "operating_income": 3_000_000_000.0,  # 10% operating margin
        },
        "dcf": {
            "terminal_growth_rate": 0.025,
            "projection_years": 5,
            "cases": [
                {"case": "low", "fcf_growth_rate": -0.05, "discount_rate": 0.11, "fcf_trajectory": [-400e6, -100e6, 500e6, 1200e6, 2000e6]},
                {"case": "base", "fcf_growth_rate": 0.05, "discount_rate": 0.09, "fcf_trajectory": [-200e6, 400e6, 1500e6, 2500e6, 3500e6]},
                {"case": "high", "fcf_growth_rate": 0.15, "discount_rate": 0.08, "fcf_trajectory": [0, 1000e6, 2500e6, 4000e6, 5500e6]},
            ],
        },
    }

    res = run_calculator(model_cyclical_trough)
    assert res["status"] == "ok"
    exp_inv = res["result"].get("expectations_investing")
    assert exp_inv is not None
    assert exp_inv.get("mode") in ("growth", "duration_at_cap", "below_floor")
    assert exp_inv.get("implied_revenue_growth_rate") is not None
    assert isinstance(exp_inv.get("implied_growth_pct"), str)
    assert "operating margin" in exp_inv.get("interpretation", "").lower()
