# Module Spec — `app/market/metrics.py`, `app/market/provider.py`, `app/market/market_data.py`

## `metrics.py` — pure deterministic functions (numpy allowed)

- `simple_return(closes: np.ndarray, n: int) -> float | None` — `(closes[-1] / closes[-1-n]) - 1`; needs at least `n+1` closes else None.
- `volume_ratio(volumes: np.ndarray, window: int = 20) -> float | None` — last volume / mean(previous `window` volumes); needs `window+1` samples else None.
- `sma_status(closes: np.ndarray, period: int) -> str` — `"above"`/`"below"` (last close vs SMA of prior `period` closes including last) or `"unavailable"` when fewer than `period` closes.
- `atr_14(highs, lows, closes) -> float | None` — donor-adapted Wilder ATR (see provenance in plan 10); needs `period+1` bars else None.
- `benchmark_relative_return(asset_return: float | None, benchmark_return: float | None) -> float | None` — difference; None when either missing.

## `provider.py` — yfinance boundary (black-box dependency)

- `PROVIDER_NAME = "yfinance"`; `DEFAULT_PERIOD = "6mo"`.
- `fetch_history(ticker, period) -> dict` — validates a yfinance-supported fetch period before calling `yfinance.Ticker(ticker).history(period=period)`. The calculated output label `3m` normalizes to fetch period `6mo`; malformed values raise `ValueError` without an upstream request. Returns `{"dates": [...], "open": [...], "high": [...], "low": [...], "close": [...], "volume": [...]}`; empty/missing data -> `MarketDataError("yfinance", ...)`.
- `fetch_info(ticker) -> dict` — subset of `Ticker().info`: `market_cap`, `shares_outstanding`, `short_interest_pct`, `currency`, `exchange`; missing keys -> None. Failures -> `MarketDataError`.
- `fetch_history_benchmark(ticker, period)` — same as `fetch_history` for benchmark.
- Tests mock the yfinance seam (`_yf_history`, `_yf_info`).

## `market_data.py` — orchestrator

- `MARKET_CAP_RELIABLE_MAX_AGE_DAYS` and similar named constants.
- `get_market_data(ticker, period=None, benchmark_ticker="SPY") -> MarketDataResult`
  - Validates ticker; fetches history + benchmark + info; each fetch failure degrades the affected fields only (returns still computed from primary history; benchmark fields `unavailable` on benchmark failure).
  - Computes derived set; builds `CalculatedField` with lookback labels `1d`,`5d`,`1m`,`3m`, `20d-vol`, `sma-50`, `sma-200`, `atr-14`, `bench-rel` and provider/as-of stamps.
  - Never returns advice/signal; never raises to outer caller except `ValueError` on invalid ticker.

## Donor code provenance

See plan 10 table: `_sma` and `_atr` adapted from `reference/stock-market-intelligence/backend/app/services/technicals.py`; yfinance is a black-box dependency.

| Local symbol | Reuse type | Exact donor location | Deliberate changes |
| --- | --- | --- | --- |
| `app.market.provider._normalize_period` | adapted | `reference/yfinance/yfinance/utils.py:496-503`, `reference/yfinance/yfinance/scrapers/history.py:105-119` | Local fixed supported-period set plus `3m` calculated-label normalization to `6mo`; no yfinance internals copied. |

## Tests

`tests/market/test_metrics.py` (exact numeric fixtures incl. insufficient history), `tests/market/test_market_data.py` (mocked seam; degrade paths; provenance stamps; no-signal guarantee).
