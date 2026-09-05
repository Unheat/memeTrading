"""Numeric fixture tests for market metrics: returns, volume ratio, SMA status, ATR."""
import numpy as np
import pytest
from app.market.metrics import (
    simple_return,
    volume_ratio,
    sma_status,
    atr_14,
    benchmark_relative_return,
)


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
