"""yfinance provider boundary (black-box dependency).

No donor code copied: yfinance is used per its public API
(`Ticker.history`, `Ticker.info`) behind these narrow seams.
"""
from __future__ import annotations

from app.market.schemas import MarketDataError

PROVIDER_NAME = "yfinance"
DEFAULT_PERIOD = "6mo"


def _yf_history(ticker: str, period: str) -> "object":  # returns pandas DataFrame
    """Seam over yfinance so tests can patch without importing pandas/yfinance."""
    import yfinance as yf

    return yf.Ticker(ticker).history(period=period)


def _yf_info(ticker: str) -> dict:
    """Seam over yfinance info dict so tests can patch it."""
    import yfinance as yf

    return yf.Ticker(ticker).info or {}


def fetch_history(ticker: str, period: str = DEFAULT_PERIOD) -> dict:
    """Fetch OHLCV history for one ticker as plain lists.

    :returns: dict with dates/open/high/low/close/volume lists (floats/strings).
    :raises MarketDataError: On empty frame or upstream failure.
    """
    try:
        frame = _yf_history(ticker, period)
    except Exception as exc:
        raise MarketDataError(PROVIDER_NAME, f"history fetch failed for {ticker}: {exc}") from exc

    try:
        if frame is None or len(frame) == 0:
            raise MarketDataError(PROVIDER_NAME, f"empty history for {ticker}")
        close_series = frame["Close"]
        dates = [str(idx) for idx in frame.index]
        return {
            "dates": dates,
            "open": [float(v) for v in frame["Open"]],
            "high": [float(v) for v in frame["High"]],
            "low": [float(v) for v in frame["Low"]],
            "close": [float(v) for v in close_series],
            "volume": [float(v) for v in frame["Volume"]],
        }
    except MarketDataError:
        raise
    except Exception as exc:
        raise MarketDataError(PROVIDER_NAME, f"history parse failed for {ticker}: {exc}") from exc


def fetch_history_benchmark(ticker: str, period: str = DEFAULT_PERIOD) -> dict:
    """Fetch OHLCV history for the benchmark ticker (same shape as fetch_history)."""
    return fetch_history(ticker, period)


def fetch_info(ticker: str) -> dict:
    """Fetch selected fundamental fields when reliably available.

    Missing fields map to None with reliable=False semantics handled by the caller.
    """
    try:
        raw = _yf_info(ticker)
    except Exception as exc:
        raise MarketDataError(PROVIDER_NAME, f"info fetch failed for {ticker}: {exc}") from exc

    def _num(key: str) -> float | None:
        value = raw.get(key)
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    return {
        "market_cap": _num("marketCap"),
        "shares_outstanding": _num("sharesOutstanding"),
        "short_interest_pct": _num("shortPercentOfFloat"),
        "currency": raw.get("currency"),
        "exchange": raw.get("exchange"),
    }
