"""Tests for the zero-redesign backtest evaluation harness."""
import pytest
from app.evaluation.backtest import (
    BacktestDecisionRecord,
    generate_date_grid,
    settle_decision,
    summarize_backtest,
)


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


def test_summarize_backtest_aggregation(monkeypatch):
    # Mock settle_decision to return controlled returns
    def fake_settle(ticker, as_of_date, forward_days=90, benchmark_ticker="SPY"):
        if ticker == "NVDA":
            return {
                "status": "settled",
                "ticker": ticker,
                "asset_return_pct": 25.0,
                "benchmark_return_pct": 5.0,
                "alpha_pct": 20.0,
                "end_price": 120.0,
            }
        elif ticker == "BAD":
            return {
                "status": "settled",
                "ticker": ticker,
                "asset_return_pct": -30.0,
                "benchmark_return_pct": 5.0,
                "alpha_pct": -35.0,
                "end_price": 50.0,
            }
        return {
            "status": "settled",
            "ticker": ticker,
            "asset_return_pct": 2.0,
            "benchmark_return_pct": 5.0,
            "alpha_pct": -3.0,
            "end_price": 95.0,
        }

    monkeypatch.setattr("app.evaluation.backtest.settle_decision", fake_settle)

    records = [
        BacktestDecisionRecord(
            ticker="NVDA",
            as_of_date="2023-01-01",
            case_id="case_1",
            status="completed",
            verdict="APPROVED_LONG_HIGH",
            bear_floor=80.0,
            current_price=100.0,
            fair_value=150.0,
        ),
        BacktestDecisionRecord(
            ticker="BAD",
            as_of_date="2023-01-01",
            case_id="case_2",
            status="completed",
            verdict="PASSED_STRICT_DISCIPLINE",
            forensic_verdict="HIGH_MANIPULATION_RISK",
            bear_floor=70.0,
            current_price=90.0,
        ),
    ]

    summary = summarize_backtest(records, forward_days=90)
    assert summary.total_runs == 2
    assert summary.approved_longs == 1
    assert summary.passed_discipline == 1
    assert summary.hit_rate_approved_longs == 1.0
    assert summary.mean_alpha_approved_longs == pytest.approx(0.20)
    assert summary.forensic_high_risk_count == 1
    assert summary.forensic_high_risk_mean_return == pytest.approx(-0.30)
    assert summary.bear_floor_breach_count == 0  # 120 > 80

    rendered = summary.render()
    assert "INSTITUTIONAL DEEP RESEARCH BACKTEST SCORECARD" in rendered
    assert "Approved Longs Hit Rate:    100.0%" in rendered
    assert "High Manipulation Risks:    1 flagged" in rendered
