# Module Spec — `app/websearch/`

## Responsibility

General web/PR/IR primary-source discovery behind `search_web(query, domains=None, limit=10) -> WebSearchResult`. Professional news stays in `search_articles`.

## `schemas.py`

- `WebRecord`: `title` (non-empty), `url` (absolute HTTP(S)), `domain` (lowercase host), `snippet` (str | None), `position` (int >= 0).
- `WebSearchResult`: `query` non-empty, `domains` tuple[str, ...] | None, `records` tuple with unique URLs, `provider`, `as_of`. Round trip via `to_dict()`/`from_dict()`.
- `WebSearchError`: structured recoverable error.

## `provider.py`

- Black-box dependency: `ddgs` (`from ddgs import DDGS`) — no API key. Wrapped in `_ddgs_text()` seam for test mocking.
- `search(query, domains=None, limit=10) -> list[WebRecord]`: filters to HTTPS results, maps title/href/body -> record, lowercases domain, dedupes by URL, returns `[]` on empty; wraps failures in `WebSearchError("duckduckgo", ...)`.

## `search.py`

- `search_web(query, domains=None, limit=10) -> WebSearchResult`: validates query/limit, calls provider, stamps provider + as-of. Never raises provider errors to outer caller beyond validation `ValueError`.

## Constraints

No API keys in MVP; no scraping/crawling (that is `read_article`'s job); no copying of donor code (no web-search donor exists; ddgs is a package dependency).

## Tests

`tests/websearch/test_websearch.py`: validation, mapping, HTTPS filter, domain restriction, dedupe, error wrapping, orchestrator round trip.
