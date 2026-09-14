# Module Spec — Keyed Free-Tier Providers (Finnhub, Apify, FRED)

## Responsibility

Optional keyed HTTPS API providers per the fullplan keyed-provider policy. Black-box dependencies with provenance recorded at the dependency boundary. The system runs fully keyless; a missing/invalid/rate-limited key disables only the affected provider and never crashes the research loop.

## `app/market/providers/finnhub.py`

- `API_KEY_ENV = "FINNHUB_API_KEY"`; `BASE_URL = "https://finnhub.io/api/v1"`.
- `FinnhubClient(api_key: str | None = None)`: constructor arg or env; `is_configured` bool; `_get(path, params) -> dict|list` seam (urllib, timeout constant, `X-Finnhub-Token` header); raises `MarketDataError("finnhub", ...)` on failure.
- `get_recommendation_trends(ticker) -> list[dict]`: `/stock/recommendation`; empty when unconfigured.
- `get_price_target(ticker) -> dict | None`: `/stock/price-target`; None when unconfigured/absent.
- `get_insider_transactions(ticker, limit=20) -> list[dict]`: `/stock/insider-transactions`; maps `data` rows to `{name, transaction_code, shares, price, change, filed_at, web_url}`; empty when unconfigured.

## `app/market/company_research.py` fallback

- `_finnhub_fallback_sections(clean_ticker, price_targets, ratings)`: when `FINNHUB_API_KEY` configured and a section is None, fill from Finnhub with `provider="finnhub"`. Unconfigured or failing Finnhub leaves sections as yfinance returned them.

## `app/social/providers/apify_twitter.py`

- `API_TOKEN_ENV = "APIFY_API_TOKEN"`; `ACTOR_ID` constant for the tweet-scraper actor; `run_sync_url(token)` builder.
- `ApifyTwitterClient(api_token=None)`: env fallback; `is_configured` property.
- `search(query, limit=25) -> list[SocialPost]`: unconfigured -> `[]` (disabled, silent). Configured: POST `run-sync-get-dataset-items` with `{searchTerms, limit}`; map items tolerantly: `post_id=f"twitter_{id}"`, `source="twitter"`, `author=author.userName`, `created_utc=createdAt` (ISO-normalized), `title` = first 60 chars of text, `score=favoriteCount`, `num_comments=replyCount`, `url`, `flair=None`. Transport failure -> `SocialProviderError("apify", ...)`.

## `app/market/providers/fred.py`

- `API_KEY_ENV = "FRED_API_KEY"`; `BASE_URL = "https://api.stlouisfed.org/fred/series/observations"`.
- `get_macro_series(series_id, limit=30) -> list[dict]`: params `series_id, api_key, file_type=json, sort_order=desc, limit`; skips `value == "."`; returns oldest->newest `{date, value}`; unconfigured -> `[]`.
- `get_macro_context(series_ids) -> dict[str, dict]`: per series `{latest_value, latest_date, observations, provider, as_of}`; failing/empty series -> explicit `{"status": "unavailable"}` entry; never raises to caller beyond `ValueError` on empty input.
- Not registered as an agent tool in Phase B (fullplan keeps nine tools).

## Constraints

- All unit tests offline: patched seams + env patches; no live API calls.
- `urllib` only (matches existing providers); named constants for timeouts/limits.
- Docstrings purpose/input/output on public functions.

## Tests

`tests/market/test_finnhub.py`, `tests/market/test_fred.py`, `tests/social/test_apify_twitter.py`; fallback case appended to `tests/market/test_company_research.py`; integration case in `tests/social/test_search.py`.
