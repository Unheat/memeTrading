"""Tests for get_market_data orchestrator with a mocked yfinance seam."""
import numpy as np
import pytest
from app.market.market_data import get_market_data
from app.market.schemas import MarketDataError


def _history(n=210, base=100.0, drift=0.001, volume=1_000_000.0) -> dict:
    """Deterministic OHLCV history fixture."""
    closes = [base * (1 + drift) ** i for i in range(n)]
    return {
        "dates": [f"2026-{(i // 21) + 1:02d}-{(i % 21) + 1:02d}" for i in range(n)],
        "open": [c * 0.99 for c in closes],
        "high": [c * 1.02 for c in closes],
        "low": [c * 0.98 for c in closes],
        "close": closes,
        "volume": [volume] * n,
    }


def _info() -> dict:
    return {"market_cap": 2.2e12, "shares_outstanding": 24.4e9, "short_interest_pct": 1.1,
            "currency": "USD", "exchange": "NASDAQ"}


def test_get_market_data_full_context():
    with patch_history(_history(), _info()), patch_history_benchmark(_history(210)):
        result = get_market_data("NVDA")

    assert result.ticker == "NVDA"
    assert result.provider == "yfinance"
    assert result.quote is not None and result.quote.price > 0
    # all four returns available with 210 bars
    for key in ("1d", "5d", "1m", "3m"):
        assert result.returns[key].status == "ok"
        assert result.returns[key].provider == "yfinance"
    assert result.volume_ratio_20d is not None and result.volume_ratio_20d.status == "ok"
    assert result.volume_ratio_20d.value == pytest.approx(1.0)  # constant volume fixture
    assert result.sma_50_status == "above"  # drifting up series
    assert result.sma_200_status == "above"
    assert result.atr_14 is not None and result.atr_14.status == "ok"
    assert result.benchmark_return is not None and result.benchmark_return.benchmark == "SPY"
    assert result.fundamentals["market_cap"] == {"value": 2.2e12, "reliable": True}


def test_get_market_data_short_history_degrades_fields():
    with patch_history(_history(n=40), _info()), patch_history_benchmark(_history(210)):
        result = get_market_data("NVDA")
    assert result.returns["3m"].status == "unavailable"  # ~63 trading days needed
    assert result.returns["1m"].status == "ok"
    assert result.sma_200_status == "unavailable"
    assert result.sma_50_status == "unavailable"  # 40 < 50


def test_get_market_data_benchmark_failure_degrades_only_benchmark():
    with patch_history(_history(), _info()), patch_history_benchmark_error():
        result = get_market_data("NVDA")
    assert result.benchmark_return is not None
    assert result.benchmark_return.status == "unavailable"
    assert result.returns["1d"].status == "ok"  # primary fields unaffected


def test_get_market_data_total_failure_raises_market_error():
    def boom(*args, **kwargs):
        raise MarketDataError("yfinance", "empty history")
    with patch_history_error():
        with pytest.raises(MarketDataError):
            get_market_data("NVDA")


def test_get_market_data_rejects_bad_ticker():
    with pytest.raises(ValueError):
        get_market_data("")
    with pytest.raises(ValueError):
        get_market_data("nv da")


from contextlib import contextmanager


@contextmanager
def patch_history(history: dict, info: dict):
    with patch_seam("app.market.market_data.fetch_history", history), \
         patch_seam("app.market.market_data.fetch_info", info):
        yield


@contextmanager
def patch_history_error():
    with patch_seam("app.market.market_data.fetch_history", None, error=MarketDataError("yfinance", "empty history")), \
         patch_seam("app.market.market_data.fetch_info", None, error=MarketDataError("yfinance", "info unavailable")):
        yield


@contextmanager
def patch_history_benchmark(history: dict):
    with patch_seam("app.market.market_data.fetch_history_benchmark", history):
        yield


@contextmanager
def patch_history_benchmark_error():
    with patch_seam("app.market.market_data.fetch_history_benchmark", None, error=MarketDataError("yfinance", "benchmark down")):
        yield


def patch_seam(target: str, value, error: Exception | None = None):
    from unittest.mock import patch
    if error is not None:
        return patch(target, side_effect=error)
    return patch(target, return_value=value)
