# Execution Plan 13 — Keyed Free-Tier Providers (Phase B)

## Purpose

Add the three optional keyed providers approved in `doc/fullplan.md` (Keyed free-tier provider policy): Finnhub, Apify (Twitter/X), FRED. Each is a black-box HTTPS API dependency with graceful degradation: a missing, invalid, or rate-limited key disables only that provider; the system must run fully keyless exactly as before.

## Donor code provenance

| Local symbol | Reuse type | Exact donor location | Deliberate changes |
| --- | --- | --- | --- |
| `app.market.providers.finnhub` | black-box dependency | Finnhub REST API v1 (`/stock/recommendation`, `/stock/price-target`, `/stock/insider-transactions`) | No donor code; wrapped behind testable seams with env-key gating. |
| `app.social.providers.apify_twitter` | black-box dependency | Apify REST API (`acts/{actor}/run-sync-get-dataset-items`) | No donor code; tolerant tweet-field mapping into `SocialPost`. |
| `app.market.providers.fred` | black-box dependency | FRED API (`/series/observations`) | No donor code; observation mapping with missing-value handling. |

## Required behavior

1. **Finnhub (`app/market/providers/finnhub.py`)**
   - `FinnhubClient(api_key=None)`: reads `FINNHUB_API_KEY` env when absent. `is_configured` property.
   - `_get(path, params)` seam; failures raise `MarketDataError("finnhub", ...)`; caller degrades.
   - `get_recommendation_trends(ticker)` -> list of `{strongBuy, buy, hold, sell, strongSell, period}` (newest first).
   - `get_price_target(ticker)` -> `{targetHigh, targetLow, targetMean, targetMedian, lastUpdated}` or None.
   - `get_insider_transactions(ticker, limit)` -> structured Form 4 supplement rows `{name, transaction_code, shares, price, change, filed_at}` (pre-parsed codes; keyless Form 4 XML parsing remains the authoritative path).
2. **Fallback wiring (`app/market/company_research.py`)**
   - yfinance first. When `FINNHUB_API_KEY` is configured and a yfinance section returned nothing, fill price targets / ratings from Finnhub with `provider="finnhub"` provenance. Insider rows are not added to `CompanyResearchResult` in Phase B (verifier-corpus supplement deferred to Phase C per fullplan).
3. **Apify Twitter (`app/social/providers/apify_twitter.py`)**
   - `ApifyTwitterClient(api_token=None)`: reads `APIFY_API_TOKEN`. Absent token -> `search()` returns `[]` silently (disabled, not an error).
   - `search(query, limit)`: sync actor run returning dataset items; tolerant field mapping (`id`, `text`, `createdAt`, `author.userName`, `favoriteCount`, `replyCount`, `url`) into `SocialPost(source="twitter")`. Provider/network failure -> `SocialProviderError("apify", ...)`.
   - `search_social` includes tweets only when configured.
4. **FRED (`app/market/providers/fred.py`)**
   - `get_macro_series(series_id, limit=30)`: latest observations as `{date, value}` with `.` missing-values skipped; missing `FRED_API_KEY` -> `[]`.
   - `get_macro_context(series_ids)` -> `{series_id: {latest_value, latest_date, observations, provider, as_of}}`; used only when a research question needs macro context; not registered as an agent tool in Phase B (fullplan keeps nine tools).

## Execution steps

1. Spec `doc/specs/market/keyed-providers.md`.
2. Red tests: `tests/market/test_finnhub.py` (incl. company-research fallback case in `test_company_research.py`), `tests/social/test_apify_twitter.py` (+ search integration in `test_search.py`), `tests/market/test_fred.py`.
3. Implement providers + wiring; green.
4. Full suite green (zero-key behavior unchanged); commit Phase B.
