"""Tests for app.market.schemas contracts."""
import pytest
from app.market.schemas import Quote, CalculatedField, MarketDataResult, MarketDataError


def _field(value=0.05, lookback="1d", benchmark=None, status="ok") -> CalculatedField:
    return CalculatedField(
        value=value,
        lookback=lookback,
        benchmark=benchmark,
        status=status,
        provider="yfinance",
        as_of="2026-09-05T20:00:00Z",
    )


def test_quote_valid_and_frozen():
    quote = Quote(
        price=182.5, previous_close=180.0, change=2.5, change_percent=1.39,
        volume=5_000_000, currency="USD", exchange="NASDAAQ", as_of="2026-09-05T20:00:00Z",
    )
    with pytest.raises(Exception):
        quote.price = 0.0


def test_quote_rejects_negative_volume():
    with pytest.raises(ValueError, match="volume"):
        Quote(price=10.0, previous_close=None, change=None, change_percent=None,
              volume=-1, currency=None, exchange=None, as_of="2026-09-05T20:00:00Z")


def test_calculated_field_ok_requires_value():
    with pytest.raises(ValueError, match="value"):
        _field(value=None, status="ok")
    unavailable = _field(value=None, status="unavailable")
    assert unavailable.value is None


def test_market_data_result_round_trip():
    result = MarketDataResult(
        ticker="NVDA",
        period="6mo",
        quote=Quote(price=182.5, previous_close=180.0, change=2.5, change_percent=1.39,
                    volume=5_000_000, currency="USD", exchange="NASDAQ", as_of="2026-09-05T20:00:00Z"),
        returns={"1d": _field(), "5d": _field(value=0.10, lookback="5d"),
                 "1m": _field(value=None, lookback="1m", status="unavailable"),
                 "3m": _field(value=None, lookback="3m", status="unavailable")},
        volume_ratio_20d=_field(value=2.1, lookback="20d-vol"),
        sma_50_status="above",
        sma_200_status="unavailable",
        atr_14=_field(value=4.2, lookback="atr-14"),
        benchmark_return=_field(value=-0.01, lookback="bench-rel", benchmark="SPY"),
        fundamentals={"market_cap": {"value": 2.2e12, "reliable": True},
                      "shares_outstanding": {"value": 24.4e9, "reliable": True},
                      "short_interest_pct": {"value": None, "reliable": False}},
        provider="yfinance",
        as_of="2026-09-05T20:00:00Z",
    )
    d = result.to_dict()
    restored = MarketDataResult.from_dict(d)
    assert restored == result


def test_market_data_result_rejects_lowercase_ticker():
    with pytest.raises(ValueError, match="ticker"):
        MarketDataResult(
            ticker="nvda", period="6mo", quote=None,
            returns={}, volume_ratio_20d=None,
            sma_50_status="unavailable", sma_200_status="unavailable",
            atr_14=None, benchmark_return=None, fundamentals=None,
            provider="yfinance", as_of="2026-09-05T20:00:00Z",
        )


def test_market_data_error():
    err = MarketDataError("yfinance", "empty history")
    assert "yfinance" in str(err)
    assert err.recoverable is True
