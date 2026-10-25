"""Unit tests for standalone LBO take-private floor model."""
from __future__ import annotations

import pytest

from app.valuation.engine import run_calculator


def test_standalone_lbo_floor_via_calculator():
    """LBO floor model runs standalone on operating income without requiring SOTP segments."""
    model = {
        "inputs": {
            "current_price": 50.0,
            "shares_diluted": 100_000_000,
            "fcf_base": 500_000_000.0,
            "operating_income": 600_000_000.0,
            "net_cash": 100_000_000.0,
            "total_debt": 400_000_000.0,
            "cash": 500_000_000.0,
        },
        "dcf": {
            "terminal_growth_rate": 0.025,
            "projection_years": 5,
            "cases": [
                {"case": "base", "fcf_growth_rate": 0.08, "discount_rate": 0.095},
            ],
        },
    }

    res = run_calculator(model)
    assert res["status"] == "ok"
    val = res["result"]
    assert "lbo_model" in val
    lbo = val["lbo_model"]
    assert lbo is not None
    assert lbo["entry_enterprise_value"] > 0
    assert lbo["sponsor_debt_capacity"] > 0
    assert lbo["sponsor_equity_check"] > 0
    assert lbo["lbo_floor_price_per_share"] is not None
    # LBO floor per share must be positive and realistic
    assert lbo["lbo_floor_price_per_share"] > 0
    assert lbo["target_irr_pct"] == "20%"
