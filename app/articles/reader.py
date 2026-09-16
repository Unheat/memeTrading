"""Paywall-safe article extraction using trafilatura.

Black-box dependency: adbar/trafilatura public API (bare_extraction).
Never bypasses paywalls; failures become structured ArticleContent statuses.
"""
from __future__ import annotations

import logging
from urllib.parse import urlparse

from app.articles.schemas import ArticleContent

logger = logging.getLogger(__name__)

# Extracted text shorter than this is treated as a failed extraction.
MIN_ARTICLE_CHARS = 120


def _bare_extraction(url: str) -> dict:
    """Thin seam over trafilatura so tests can patch without importing it."""
    from trafilatura import bare_extraction

    return bare_extraction(
        url,
        with_metadata=True,
        favor_recall=True,
        url_blacklist=None,
        no_fallback=False,
    )


def _is_https(url: str) -> bool:
    """Return True only for absolute HTTPS URLs."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme == "https" and bool(parsed.netloc)


def _coerce(value) -> str | None:
    """Convert trafilatura metadata values to plain strings or None."""
    if value is None:
        return None
    return str(value)


def read_article(url: str) -> ArticleContent:
    """Fetch and extract cleaned article text for one URL.

    :param url: Absolute HTTPS URL of the article.
    :returns: ArticleContent with status ok/paywalled/unavailable/extraction_failed.
              Never raises to the outer caller; never bypasses paywalls.
    """
    if not _is_https(url):
        return ArticleContent(
            url=url,
            title=url,
            text="",
            author=None,
            published_utc=None,
            site_name=None,
            status="unavailable",
            extraction_note="URL is not absolute HTTPS; refusing to fetch.",
        )

    try:
        raw = _bare_extraction(url)
    except Exception as exc:
        logger.warning("Article extraction failed for %s: %s", url, exc)
        return ArticleContent(
            url=url,
            title=url,
            text="",
            author=None,
            published_utc=None,
            site_name=None,
            status="unavailable",
            extraction_note=f"fetch/extraction error: {exc}",
        )

    if not raw:
        return ArticleContent(
            url=url,
            title=url,
            text="",
            author=None,
            published_utc=None,
            site_name=None,
            status="extraction_failed",
            extraction_note="extractor returned no content (likely paywall or non-article page)",
        )

    text = _coerce(raw.get("text")) or ""
    title = _coerce(raw.get("title")) or url

    if len(text.strip()) < MIN_ARTICLE_CHARS:
        return ArticleContent(
            url=url,
            title=title,
            text="",
            author=_coerce(raw.get("author")),
            published_utc=_coerce(raw.get("date")),
            site_name=_coerce(raw.get("sitename")),
            status="paywalled",
            extraction_note="extracted text too short; likely paywalled or truncated",
        )

    return ArticleContent(
        url=url,
        title=title,
        text=text,
        author=_coerce(raw.get("author")),
        published_utc=_coerce(raw.get("date")),
        site_name=_coerce(raw.get("sitename")),
        status="ok",
        extraction_note=None,
    )
