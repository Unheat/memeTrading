# Module Spec — `app/articles/schemas.py`

## Responsibility

Immutable validated records for professional article search results and extracted article content. No network, filesystem, or parsing logic.

## Public contracts

### `ArticleRecord`
- `article_id`: lowercase sha1 hex of normalized URL (non-empty).
- `title`: non-empty string.
- `publisher`: non-empty display name (e.g. `"wsj"`, `"cnbc"`, `"gdelt:<domain>"`).
- `published_utc`: ISO-8601 string or None when feed/API omits it.
- `url`: HTTP(S) absolute URL.
- `summary`: RSS description/metadata snippet or None. Never fabricated.
- `domain`: hostname (lowercase) or None.
- `source`: literal `"rss"` or `"gdelt"`.
- `access_status`: literal `"ok"`, `"metadata_only"`, `"paywalled"`, `"unavailable"`.
- Invalid input raises `ValueError`.

### `ArticleContent`
- `url`: non-empty string (echoed caller input; may be invalid when status is `unavailable`).
- `title` (non-empty), `text` (may be empty only when status is not `"ok"`).
- `author`, `published_utc`, `site_name`: optional metadata from extraction, None when absent.
- `status`: literal `"ok"`, `"paywalled"`, `"unavailable"`, `"extraction_failed"`.
- `extraction_note`: short human-readable reason when status is not `"ok"`.
- `status="ok"` requires non-empty text. Invalid input raises `ValueError`.

### `ArticleSearchResult`
- `query` non-empty, `ticker` uppercase or None, `days` positive int, `records` tuple of `ArticleRecord` with unique `url` values, `source_summary` dict source->count.
- `to_dict()`/`from_dict()` round trip with validation.

### `ArticleProviderError`
`Exception` subclass with `provider`, `message`, `recoverable: bool = True`; `str()` form `"[provider] message (recoverable=True)"`.

## Constraints

- Standard library only. No feedparser/gdeltdoc/trafilatura/requests imports.
- Every public method has purpose/input/output docstrings.
- Named constants at module top for any thresholds.

## Donor code provenance

No donor code copied; these are local contracts owned by this project.

## Tests

`tests/articles/test_schemas.py`: validation rules, frozen-ness, round trips, unique-URL enforcement.
