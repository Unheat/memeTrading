# Execution Plan 09 — Professional Article Search & Read (`search_articles`, `read_article`)

## Purpose

Implement the two professional-news outer-agent tools from `doc/fullplan.md` (Step 6):

- `search_articles(query, ticker=None, sources=None, days=7, limit=20) -> ArticleSearchResult`
- `read_article(url) -> ArticleContent`

They find professional financial news (RSS + GDELT discovery) and fetch cleaned article text without ever bypassing paywalls.

## Boundaries

- Professional articles are attributable human analysis, not facts; the outer agent compares them with other sources.
- Paywalled content is never bypassed. Preserve usable RSS headline/description metadata and mark access status explicitly (`metadata_only` / `paywalled` / `unavailable` / `ok`).
- No article RAG corpus. `read_article` is live research only.
- Do not expose every publisher as a separate tool; provider details stay inside the implementation.
- Tests are deterministic and offline: fixture RSS XML and fixture GDELT JSON, no live network.

## Donor code provenance

| Local symbol | Reuse type | Exact donor location | Deliberate changes |
| --- | --- | --- | --- |
| `app/articles/providers/rss.py` feed registry | adapted | `reference/finance-news-aggregator/finnews/wsj.py:26` (URL template pattern), plus sibling publisher adapters (`cnbc.py`, `market_watch.py`, `nasdaq.py`, `yahoo_finance.py`) | Keep only publisher feed URL constants; parse with `feedparser` instead of finnews's requests+defusedxml parser; normalize entries into `ArticleRecord` with access-status. finnews client classes/parser/cache not reused. |
| `app/articles/providers/gdelt.py` | adapted | `reference/gdelt-doc-api/gdeltdoc/api_client.py:44-62`, `GdeltDoc.article_search` | Black-box dependency use of `gdeltdoc` (normal package/API call, not copied code); wrap in structured error boundary and map DataFrame rows to `ArticleRecord`. |
| `app/articles/reader.py` | black-box dependency | `adbar/trafilatura` `bare_extraction`/`extract` public API | No donor code copied; trafilatura used per its public API for extraction only. |

## Required behavior

1. **Schemas (`app/articles/schemas.py`)**
   - `ArticleRecord`: frozen — `article_id` (sha1 of URL), `title`, `publisher`, `published_utc` (ISO or None), `url`, `summary` (RSS description or None), `domain`, `source` (`rss` | `gdelt`), `access_status` (`ok` | `metadata_only` | `paywalled` | `unavailable`).
   - `ArticleContent`: frozen — `url`, `title`, `text`, `author`, `published_utc`, `site_name`, `status` (`ok` | `paywalled` | `unavailable` | `extraction_failed`), `extraction_note`.
   - `ArticleSearchResult`: frozen — `query`, `ticker`, `days`, `records` (tuple, deduplicated by URL, newest-first), `source_summary`.
   - `ArticleProviderError`: structured recoverable error (`provider`, `message`).
   - All records `to_dict()`/`from_dict()` JSON round trips with validation re-applied.

2. **RSS provider (`app/articles/providers/rss.py`)**
   - Feed registry: publisher name -> feed URL(s) adapted from finnews adapters (WSJ, CNBC, MarketWatch, Nasdaq, Yahoo Finance).
   - `fetch_feeds(urls, days, limit) -> list[ArticleRecord]` using `feedparser`; entry title/link/published/description -> record; entries older than `days` dropped; missing link or title skipped.
   - Paywall-aware: known-paywalled publishers (WSJ) get `access_status="metadata_only"` from search time.

3. **GDELT provider (`app/articles/providers/gdelt.py`)**
   - `search(query, days, limit) -> list[ArticleRecord]` wrapping `GdeltDoc.article_search(Filters(...))`; map url/title/seendate/domain; wrap import/requests failures into `ArticleProviderError`.

4. **Reader (`app/articles/reader.py`)**
   - `read_article(url) -> ArticleContent` via trafilatura `bare_extraction` with metadata. HTTPS-only URL validation. Empty/too-short extraction -> `status="extraction_failed"` (or `"paywalled"` when the page signals a paywall); never fetches or fabricates bypassed text.
   - Timeout-bounded fetch; network failures -> `status="unavailable"`, never raw exception to outer caller.

5. **Orchestrator (`app/articles/search.py`)**
   - `search_articles(query, ticker=None, sources=None, days=7, limit=20)`:
     validates query non-empty; queries GDELT (query-driven) + RSS (topic feeds, optionally filtered by `sources`); merges, deduplicates by URL, sorts newest-first; truncates to `limit`; one provider failing never fails the whole result.

## Files

```text
app/articles/__init__.py
app/articles/schemas.py
app/articles/metrics-free module: none (no statistics in this slice)
app/articles/providers/__init__.py
app/articles/providers/rss.py
app/articles/providers/gdelt.py
app/articles/reader.py
app/articles/search.py
tests/articles/test_schemas.py
tests/articles/test_rss.py
tests/articles/test_gdelt.py
tests/articles/test_reader.py
tests/articles/test_search.py
doc/specs/articles/schemas.md
doc/specs/articles/providers.md
```

## Dependencies

Add to `requirements.txt`: `feedparser>=6,<7`, `gdeltdoc>=1,<2`, `trafilatura>=1.12,<2`.

## Execution steps

1. Write `doc/specs/articles/schemas.md` and `doc/specs/articles/providers.md`.
2. Red tests schemas -> implement -> green.
3. Red tests RSS + GDELT providers (fixtures, mocked transport) -> implement -> green.
4. Red tests reader (fixture HTML via mocked trafilatura fetch) -> implement -> green.
5. Red tests orchestrator -> implement -> green.
6. Full suite green; compile; commit milestone.
