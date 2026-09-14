"""Numeric fixture tests for market metrics: returns, volume ratio, SMA status, ATR."""
import numpy as np
import pytest
from app.market.metrics import (
    simple_return,
    volume_ratio,
    sma_status,
    atr_14,
    benchmark_relative_return,
    average_daily_dollar_volume,
    market_cap_tier,
    compute_fractional_kelly,
)


def test_compute_fractional_kelly():
    # 3:1 asymmetry: +45% upside, 15% downside, 60% win prob -> hits 8% single-name cap
    size = compute_fractional_kelly(upside_pct=0.45, downside_pct=0.15, win_prob=0.60, fraction=0.25)
    assert size == pytest.approx(0.08)

    # Low asymmetry: +10% upside, 20% downside -> negative expectancy -> 0%
    size_bad = compute_fractional_kelly(upside_pct=0.10, downside_pct=0.20, win_prob=0.50)
    assert size_bad == 0.0

    # High downside risk constrained by max loss budget (e.g. 50% downside with 5% loss budget -> <= 10%)
    size_risk = compute_fractional_kelly(upside_pct=2.0, downside_pct=0.70, win_prob=0.60, max_position_cap=0.20, max_loss_budget=0.05)
    assert size_risk <= 0.05 / 0.70


def test_average_daily_dollar_volume():
    closes = np.full(25, 100.0)
    volumes = np.full(25, 50_000.0)
    # last 20 days: 100 * 50_000 = 5,000,000
    assert average_daily_dollar_volume(closes, volumes, window=20) == pytest.approx(5_000_000.0)


def test_average_daily_dollar_volume_insufficient():
    closes = np.full(10, 100.0)
    volumes = np.full(10, 50_000.0)
    assert average_daily_dollar_volume(closes, volumes, window=20) is None


def test_market_cap_tier():
    assert market_cap_tier(2.5e12) == "mega"
    assert market_cap_tier(50e9) == "large"
    assert market_cap_tier(5e9) == "mid"
    assert market_cap_tier(500e6) == "small"
    assert market_cap_tier(50e6) == "micro"
    assert market_cap_tier(None) == "unknown"
    assert market_cap_tier(-1) == "unknown"


def test_simple_return_exact():
    closes = np.array([100.0, 102.0, 104.0, 106.0, 110.0])
    # 1d: 110/106 - 1
    assert simple_return(closes, 1) == pytest.approx(110.0 / 106.0 - 1)
    # 4d: 110/100 - 1
    assert simple_return(closes, 4) == pytest.approx(0.10)


def test_simple_return_insufficient_history():
    closes = np.array([100.0, 101.0])
    assert simple_return(closes, 5) is None
    assert simple_return(np.array([]), 1) is None


def test_volume_ratio_exact():
    volumes = np.array([100.0] * 20 + [300.0])
    # last 300 vs mean of previous 20 (100)
    assert volume_ratio(volumes, window=20) == pytest.approx(3.0)


def test_volume_ratio_insufficient():
    volumes = np.array([100.0, 200.0])
    assert volume_ratio(volumes, window=20) is None


def test_sma_status_above_and_below():
    # rising series: last close above 50-day mean
    rising = np.concatenate([np.full(50, 100.0), [120.0]])
    assert sma_status(rising, 50) == "above"
    falling = np.concatenate([np.full(50, 100.0), [80.0]])
    assert sma_status(falling, 50) == "below"


def test_sma_status_insufficient():
    assert sma_status(np.array([100.0, 101.0]), 50) == "unavailable"


def test_atr_14_constant_range():
    n = 40
    highs = np.full(n, 105.0)
    lows = np.full(n, 95.0)
    closes = np.full(n, 100.0)
    # TR = 10 every bar -> ATR = 10
    assert atr_14(highs, lows, closes) == pytest.approx(10.0)


def test_atr_14_insufficient_history():
    highs = np.array([105.0, 106.0])
    lows = np.array([95.0, 96.0])
    closes = np.array([100.0, 101.0])
    assert atr_14(highs, lows, closes) is None


def test_atr_14_true_range_uses_prior_close():
    # Closes alternate 100/95 while highs/lows stay 105/95 — TR stays exactly 10
    # because the |high - prev_close| and |low - prev_close| legs are exercised.
    n = 40
    highs = np.full(n, 105.0)
    lows = np.full(n, 95.0)
    closes = np.array([100.0 if i % 2 == 0 else 95.0 for i in range(n)])
    result = atr_14(highs, lows, closes)
    assert result == pytest.approx(10.0, rel=1e-6)


def test_benchmark_relative_return():
    assert benchmark_relative_return(0.05, 0.01) == pytest.approx(0.04)
    assert benchmark_relative_return(None, 0.01) is None
    assert benchmark_relative_return(0.05, None) is None
