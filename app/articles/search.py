"""Outer-agent article search orchestrator: search_articles tool."""
from __future__ import annotations

import logging

from app.articles.providers.gdelt import search as gdelt_search
from app.articles.providers.rss import search_rss
from app.articles.schemas import ArticleRecord, ArticleSearchResult

logger = logging.getLogger(__name__)


def search_articles(
    query: str,
    ticker: str | None = None,
    sources: list[str] | None = None,
    days: int = 7,
    limit: int = 20,
) -> ArticleSearchResult:
    """Search professional financial news via GDELT discovery plus RSS feeds.

    :param query: Non-empty search keywords.
    :param ticker: Optional ticker to attach to the result (uppercase).
    :param sources: Optional publisher-name filter for RSS feeds.
    :param days: Lookback window in days (positive).
    :param limit: Maximum records returned (positive).
    :returns: ArticleSearchResult with deduplicated, newest-first records.
    :raises ValueError: On invalid query/days/limit.
    """
    if not query or not query.strip():
        raise ValueError("query must be a non-empty string")
    if days <= 0:
        raise ValueError("days must be positive")
    if limit <= 0:
        raise ValueError("limit must be positive")

    clean_query = query.strip()
    clean_ticker = ticker.upper().strip() if ticker else None

    # GDELT: query-driven cross-domain discovery.
    try:
        gdelt_records = gdelt_search(clean_query, days=days, limit=limit)
    except Exception as exc:
        logger.warning("GDELT provider failed during search_articles: %s", exc)
        gdelt_records = []

    # RSS: curated professional feeds, optional publisher filter.
    try:
        rss_records = search_rss(sources, days=days, limit=limit)
    except Exception as exc:
        logger.warning("RSS provider failed during search_articles: %s", exc)
        rss_records = []

    # Merge and dedupe by URL (first occurrence wins: RSS before GDELT keeps
    # the richer record with publisher + summary).
    seen_urls: set[str] = set()
    merged: list[ArticleRecord] = []
    for record in rss_records + gdelt_records:
        if record.url in seen_urls:
            continue
        seen_urls.add(record.url)
        merged.append(record)

    # Newest first; records without a date go last.
    newest_first = sorted(
        merged,
        key=lambda r: r.published_utc or "",
        reverse=True,
    )

    truncated = newest_first[:limit]
    source_summary: dict[str, int] = {}
    for record in truncated:
        key = record.source
        source_summary[key] = source_summary.get(key, 0) + 1

    return ArticleSearchResult(
        query=clean_query,
        ticker=clean_ticker,
        days=days,
        records=tuple(truncated),
        source_summary=source_summary,
    )
