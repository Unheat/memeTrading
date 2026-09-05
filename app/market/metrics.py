"""Deterministic market-context metrics.

`sma_series` and `atr_14` adapted from donor:
reference/stock-market-intelligence/backend/app/services/technicals.py (_sma:26-31, _atr:92-102).
Only these compact functions are ported; EMA/RSI/MACD/Bollinger are excluded from MVP.
"""
from __future__ import annotations

import numpy as np

ATR_PERIOD = 14
VOLUME_WINDOW = 20


def simple_return(closes: np.ndarray, n: int) -> float | None:
    """Return the n-trading-day simple return, or None with insufficient history."""
    if len(closes) < n + 1 or n <= 0:
        return None
    base = float(closes[-1 - n])
    if base == 0.0:
        return None
    return float(closes[-1] / base - 1.0)


def volume_ratio(volumes: np.ndarray, window: int = VOLUME_WINDOW) -> float | None:
    """Return last volume divided by the mean of the previous `window` volumes."""
    if len(volumes) < window + 1:
        return None
    baseline = float(np.mean(volumes[-(window + 1):-1]))
    if baseline == 0.0:
        return None
    return float(volumes[-1] / baseline)


def sma_status(closes: np.ndarray, period: int) -> str:
    """Return 'above'/'below' for last close vs its `period`-day SMA, else 'unavailable'."""
    if len(closes) < period:
        return "unavailable"
    window = closes[-period:]
    sma = float(np.mean(window))
    return "above" if float(closes[-1]) >= sma else "below"


def atr_14(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = ATR_PERIOD) -> float | None:
    """Return the last Wilder-smoothed ATR value, or None with insufficient history.

    Donor-adapted from reference/stock-market-intelligence/backend/app/services/technicals.py:_atr.
    """
    n = len(closes)
    if n < period + 1 or len(highs) != n or len(lows) != n:
        return None
    tr = np.zeros(n)
    tr[0] = highs[0] - lows[0]
    for i in range(1, n):
        tr[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
    atr = np.zeros_like(tr)
    atr[period - 1] = np.mean(tr[:period])
    for i in range(period, n):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    return float(atr[-1])


def benchmark_relative_return(asset_return: float | None, benchmark_return: float | None) -> float | None:
    """Return asset minus benchmark, or None when either side is missing."""
    if asset_return is None or benchmark_return is None:
        return None
    return asset_return - benchmark_return
