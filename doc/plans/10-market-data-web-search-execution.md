# Execution Plan 10 — Market Data & Web Search (`get_market_data`, `search_web`)

## Purpose

Implement the two remaining MVP research tools from `doc/fullplan.md` (Step 7):

- `get_market_data(ticker, period=None) -> MarketDataResult` — compact market context via yfinance.
- `search_web(query, domains=None) -> WebSearchResult` — general web/PR/IR primary-source discovery.

## Boundaries

- Market context is pricing evidence only: it can never prove a business claim, produce a buy/sell signal, or act as a forecast.
- Derived set stays deliberately compact: 1-day/5-day/1-month/3-month returns, 20-day volume ratio, 50/200-day SMA trend status, 14-day ATR. RSI/MACD/Bollinger are excluded from MVP.
- Every raw and calculated field declares provider, as-of time, lookback/benchmark where applicable, and availability status.
- `search_web` covers company/counterparty sites, IR pages, press releases, regulatory announcements; professional news stays with `search_articles`.
- Tests are deterministic and offline; yfinance/DDG seams are mocked.

## Donor code provenance

| Local symbol | Reuse type | Exact donor location | Deliberate changes |
| --- | --- | --- | --- |
| `app/market/metrics.py` `sma_series` | adapted | `reference/stock-market-intelligence/backend/app/services/technicals.py:26-31`, `_sma` | Vectorized rolling mean via numpy stride logic retained but returns full array with NaN head; used only for 50/200-day status. |
| `app/market/metrics.py` `atr_series` | adapted | `reference/stock-market-intelligence/backend/app/services/technicals.py:92-102`, `_atr` | Same True Range + Wilder smoothing; used only for 14-day ATR (last value). |
| `app/market/provider.py` | black-box dependency | `ranaroussi/yfinance` public API (`Ticker.history`, `.info`) | Not copied code; wrapped behind structured provider boundary. |
| `app/websearch/provider.py` | black-box dependency | `ddgs` (DuckDuckGo search) public API | Not copied code; wrapped behind structured provider boundary. |
| `reference/alpha_vantage/` | rejected for MVP | N/A | Per fullplan: optional fallback only after real free-tier smoke test; not an MVP dependency. |

## Required behavior

1. **Schemas (`app/market/schemas.py`)**
   - `Quote`: normalized last price, previous close, change, change percent, volume, currency, exchange, as-of timestamp.
   - `CalculatedField`: value or None, `lookback` label, `benchmark` or None, `status` (`ok`/`unavailable`), plus provider/as-of inherited.
   - `MarketDataResult`: ticker, quote, `returns` dict (1d/5d/1m/3m `CalculatedField`), `volume_ratio_20d`, `sma_50_status`/`sma_200_status` (`above`/`below`/`unavailable`), `atr_14`, benchmark-relative return, `shares_outstanding`/`market_cap`/`short_interest` when reliably available, provider, as-of, per-field calculation status. `to_dict()`/`from_dict()`.
   - `MarketDataError`: structured recoverable error.

2. **Metrics (`app/market/metrics.py`)** — pure functions, numpy:
   - `simple_return(closes, n)` — n-trading-day return.
   - `volume_ratio(volumes, window=20)`.
   - `sma_status(closes, period)` -> `above`/`below`/`unavailable`.
   - `atr_14(highs, lows, closes)` (donor-adapted).
   - Insufficient history -> `None` (rendered as `unavailable`).

3. **Provider (`app/market/provider.py`)**
   - `fetch_history(ticker, period) -> dict` via `yfinance.Ticker.history(period=...)` returning OHLCV arrays; `fetch_info(ticker)` for market cap/shares/short interest when reliable (explicit `None` otherwise).
   - Missing ticker / empty frame / network failure -> `MarketDataError`, never raw exceptions.

4. **Orchestrator (`app/market/market_data.py`)**
   - `get_market_data(ticker, period=None, benchmark_ticker="SPY") -> MarketDataResult`: fetch history + info, compute derived set (incl. benchmark-relative return), stamp provenance, degrade per-field to `unavailable` when data missing. Never emits a signal or recommendation.

5. **Web search (`app/websearch/`)**
   - `schemas.py`: `WebRecord` (title/url/domain/snippet/position), `WebSearchResult` (query, optional domains, records, as-of), `WebSearchError`.
   - `provider.py`: `ddgs` black-box wrapper; HTTPS URL filter; domain-restriction support; empty/blocked result -> empty list or structured error.
   - `search.py`: `search_web(query, domains=None, limit=10) -> WebSearchResult`, validation + dedupe by URL.

## Files

```text
app/market/__init__.py  app/market/schemas.py  app/market/metrics.py
app/market/provider.py  app/market/market_data.py
app/websearch/__init__.py  app/websearch/schemas.py  app/websearch/provider.py  app/websearch/search.py
tests/market/test_schemas.py  tests/market/test_metrics.py  tests/market/test_market_data.py
tests/websearch/test_websearch.py
doc/specs/market/schemas.md  doc/specs/market/metrics-provider.md  doc/specs/websearch/search.md
```

## Dependencies

Add to `requirements.txt`: `yfinance>=0.2,<1`, `ddgs>=9,<10`.

## Execution steps

1. Write specs (`doc/specs/market/`, `doc/specs/websearch/`).
2. Red tests schemas -> implement -> green.
3. Red tests metrics (exact numeric fixtures) -> implement -> green.
4. Red tests provider+orchestrator (mocked yfinance) -> implement -> green.
5. Red tests web search (mocked ddgs) -> implement -> green.
6. Full suite green; compile; commit milestone.
