# Module Spec — `app/articles/providers/` and `app/articles/reader.py`, `app/articles/search.py`

## Responsibility

Network adapters for professional article discovery (RSS + GDELT), paywall-safe article extraction, and the `search_articles` orchestrator. Provider details stay hidden behind normalized records.

## `providers/rss.py`

- `RSS_FEED_REGISTRY`: dict publisher -> list of feed URLs, adapted from finnews adapters (WSJ, CNBC, MarketWatch, Nasdaq, Yahoo Finance). Named constant.
- `PAYWALLED_PUBLISHERS`: frozenset of publisher names that serve only headline/description in RSS (WSJ). Named constant.
- `fetch_feeds(feed_urls: list[tuple[str, str]], days: int, limit: int) -> list[ArticleRecord]`
  - Input: (publisher, url) pairs; uses `feedparser` as black-box dependency.
  - Skips entries without link or title; parses `published_parsed` to UTC ISO when present; drops entries older than `days`.
  - `summary` = entry description only (never fetched extra); publisher in `PAYWALLED_PUBLISHERS` -> `access_status="metadata_only"`, else `"ok"`.
  - Transport/parse failure of one feed -> skip that feed, log, never raise to caller.
- `search_rss(sources: list[str] | None, days: int, limit: int) -> list[ArticleRecord]` selects registry entries filtered by publisher names when `sources` given.

## `providers/gdelt.py`

- `search(query: str, days: int, limit: int) -> list[ArticleRecord]`
  - Wraps `gdeltdoc.GdeltDoc.article_search(Filters(keyword=..., start_date, end_date))` as a black-box dependency (recorded in dependency boundary, not copied code).
  - DataFrame rows (`url`, `title`, `seendate`, `domain`) mapped to `ArticleRecord(source="gdelt", publisher=f"gdelt:{domain}", access_status="ok")`.
  - Direct inputs require non-empty query, positive `days`, and positive `limit`; provider requests use `num_records=min(limit, 250)`.
  - Empty result -> empty list. Any exception -> `ArticleProviderError("gdelt", ...)`; no raw exceptions leak.

## `reader.py`

- `MAX_ARTICLE_CHARS`, `FETCH_TIMEOUT_SECONDS` named constants.
- `read_article(url: str) -> ArticleContent`
  - HTTPS-only absolute URL; else `status="unavailable"`.
  - Public `from trafilatura import bare_extraction` import with metadata (black-box dependency per public API).
  - `status="ok"` when text extracted (non-empty, >= `MIN_ARTICLE_CHARS`); `"extraction_failed"` when empty/short; `"paywalled"` when extraction is blocked/partial per trafilatura signals or known paywall metadata — text is never bypassed or fabricated; `"unavailable"` on network failure.
  - Never raises to outer caller; all failures become structured `ArticleContent` with `extraction_note`.

## `search.py`

- `search_articles(query, ticker=None, sources=None, days=7, limit=20) -> ArticleSearchResult`
  - Validates non-empty query, positive days/limit.
  - Runs GDELT search + RSS search; each wrapped so one provider failure degrades instead of failing.
  - Merge, dedupe by URL (keep newest/first), sort newest-first (missing dates last), truncate to `limit`, build `source_summary`.
- `MAX_FEED_ENTRIES` named constant caps per-feed work.

## Constraints

- No live network in unit tests; fixture XML/JSON and mocked transport/extraction only.
- No article RAG corpus, no caching layer, no publisher-specific outer tools.

## Donor code provenance

See `doc/plans/09-article-search-read-execution.md` table: finnews feed-URL registry adapted; gdeltdoc and trafilatura are black-box dependencies.

| Local symbol | Reuse type | Exact donor location | Deliberate changes |
| --- | --- | --- | --- |
| `app.articles.providers.gdelt.search` request validation | adapted | `reference/gdelt-doc-api/gdeltdoc/api_client.py:65-84,130-178`, `reference/gdelt-doc-api/gdeltdoc/filters.py:91-109,233-247` | Bounded local inputs and `num_records`; preserves black-box `gdeltdoc` call and normalized error contract. |

## Tests

`tests/articles/test_rss.py`, `test_gdelt.py`, `test_reader.py`, `test_search.py` — fixtures + mocks; failure-mode coverage for provider outage, empty feeds, short extraction, dedupe and ordering.
