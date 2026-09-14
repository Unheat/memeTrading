"""Outer-agent market-context orchestrator: get_market_data tool."""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from app.market import metrics
from app.market.provider import (
    DEFAULT_PERIOD,
    PROVIDER_NAME,
    fetch_history,
    fetch_history_benchmark,
    fetch_info,
)
from app.market.schemas import (
    CalculatedField,
    MarketDataError,
    MarketDataResult,
    Quote,
    _unavailable_field,
)

# Trading days used for month-scale return lookbacks.
MONTH_LOOKBACK = 21
THREE_MONTH_LOOKBACK = 63

TICKER_ALLOWED_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.^-")


def _validate_ticker(ticker: str) -> str:
    """Normalize and validate a caller-supplied ticker."""
    clean = (ticker or "").strip().upper()
    if not clean or any(ch not in TICKER_ALLOWED_CHARS for ch in clean):
        raise ValueError(f"invalid ticker: {ticker!r}")
    return clean


def _field(value: float | None, lookback: str, as_of: str, benchmark: str | None = None) -> CalculatedField:
    """Wrap a metric result into a provenance-stamped CalculatedField."""
    if value is None:
        return _unavailable_field(lookback, benchmark, PROVIDER_NAME, as_of)
    return CalculatedField(
        value=value, lookback=lookback, benchmark=benchmark,
        status="ok", provider=PROVIDER_NAME, as_of=as_of,
    )


def get_market_data(
    ticker: str,
    period: str | None = None,
    benchmark_ticker: str = "SPY",
) -> MarketDataResult:
    """Return compact market context for one ticker; never a signal or advice.

    :param ticker: Uppercase ticker symbol.
    :param period: yfinance history period (default 6mo).
    :param benchmark_ticker: Benchmark for relative return (default SPY).
    :returns: MarketDataResult with per-field provenance and availability.
    :raises ValueError: On invalid ticker.
    :raises MarketDataError: When primary history cannot be fetched at all.
    """
    clean_ticker = _validate_ticker(ticker)
    effective_period = period or DEFAULT_PERIOD
    as_of = datetime.now(timezone.utc).isoformat()

    history = fetch_history(clean_ticker, effective_period)
    closes = np.array(history["close"], dtype=float)
    volumes = np.array(history["volume"], dtype=float)
    highs = np.array(history["high"], dtype=float)
    lows = np.array(history["low"], dtype=float)

    # Quote
    quote = None
    if len(closes) >= 1:
        prev = float(closes[-2]) if len(closes) >= 2 else None
        change = float(closes[-1] - prev) if prev is not None else None
        change_pct = (change / prev) if (change is not None and prev) else None
        last_volume = float(volumes[-1]) if len(volumes) else None
        info_cache = None
        try:
            info_cache = fetch_info(clean_ticker)
        except MarketDataError:
            info_cache = None
        quote = Quote(
            price=float(closes[-1]),
            previous_close=prev,
            change=change,
            change_percent=round(change_pct, 6) if change_pct is not None else None,
            volume=last_volume,
            currency=info_cache.get("currency") if info_cache else None,
            exchange=info_cache.get("exchange") if info_cache else None,
            as_of=as_of,
        )

    # Returns
    returns = {
        "1d": _field(metrics.simple_return(closes, 1), "1d", as_of),
        "5d": _field(metrics.simple_return(closes, 5), "5d", as_of),
        "1m": _field(metrics.simple_return(closes, MONTH_LOOKBACK), "1m", as_of),
        "3m": _field(metrics.simple_return(closes, THREE_MONTH_LOOKBACK), "3m", as_of),
    }

    # Volume ratio / ATR / SMA statuses / Liquidity (ADDV)
    volume_ratio_field = _field(metrics.volume_ratio(volumes), "20d-vol", as_of)
    atr_field = _field(metrics.atr_14(highs, lows, closes), "atr-14", as_of)
    sma_50_status = metrics.sma_status(closes, 50)
    sma_200_status = metrics.sma_status(closes, 200)
    addv_val = metrics.average_daily_dollar_volume(closes, volumes)
    addv_field = _field(addv_val, "20d-addv", as_of)

    # Benchmark-relative return: primary 1m return vs benchmark 1m return.
    benchmark_return = None
    try:
        bench_history = fetch_history_benchmark(benchmark_ticker, effective_period)
        bench_closes = np.array(bench_history["close"], dtype=float)
        asset_1m = returns["1m"].value
        bench_1m = metrics.simple_return(bench_closes, MONTH_LOOKBACK)
        rel = metrics.benchmark_relative_return(asset_1m, bench_1m)
        benchmark_return = _field(rel, "bench-rel", as_of, benchmark=benchmark_ticker)
    except MarketDataError:
        benchmark_return = _unavailable_field("bench-rel", benchmark_ticker, PROVIDER_NAME, as_of)

    # Fundamentals (reliability: present-and-numeric = reliable)
    fundamentals = None
    mkt_cap = None
    try:
        info = fetch_info(clean_ticker)
        mkt_cap = info.get("market_cap")
        fundamentals = {
            "market_cap": {"value": mkt_cap, "reliable": mkt_cap is not None},
            "shares_outstanding": {"value": info.get("shares_outstanding"), "reliable": info.get("shares_outstanding") is not None},
            "short_interest_pct": {"value": info.get("short_interest_pct"), "reliable": info.get("short_interest_pct") is not None},
        }
    except MarketDataError:
        fundamentals = None

    cap_tier = metrics.market_cap_tier(mkt_cap)

    return MarketDataResult(
        ticker=clean_ticker,
        period=effective_period,
        quote=quote,
        returns=returns,
        volume_ratio_20d=volume_ratio_field,
        sma_50_status=sma_50_status,
        sma_200_status=sma_200_status,
        atr_14=atr_field,
        benchmark_return=benchmark_return,
        fundamentals=fundamentals,
        provider=PROVIDER_NAME,
        as_of=as_of,
        addv_20d=addv_field,
        cap_tier=cap_tier,
    )
