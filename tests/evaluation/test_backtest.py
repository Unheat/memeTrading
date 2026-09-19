"""Tests for the zero-redesign backtest evaluation harness."""
import pytest
from app.evaluation.backtest import generate_date_grid, settle_decision


def test_generate_date_grid_valid():
    dates = generate_date_grid("2023-01-01", "2023-04-01", every_n_days=30)
    assert len(dates) >= 4
    assert dates[0] == "2023-01-01"
    assert dates[1] == "2023-01-31"


def test_generate_date_grid_invalid_order():
    with pytest.raises(ValueError, match="cannot be before"):
        generate_date_grid("2024-01-01", "2023-01-01", every_n_days=30)


def test_generate_date_grid_invalid_step():
    with pytest.raises(ValueError, match="at least 1"):
        generate_date_grid("2023-01-01", "2023-04-01", every_n_days=0)


def test_settle_decision_future_date():
    # If settlement date falls in the future, should return pending_settlement
    res = settle_decision("AAPL", as_of_date="2026-08-01", forward_days=90)
    assert res.get("status") == "pending_settlement"
