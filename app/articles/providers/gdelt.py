"""GDELT article discovery provider.

Black-box dependency: gdeltdoc package (GdeltDoc.article_search / Filters).
No donor code copied; rows are mapped into normalized ArticleRecord values.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from app.articles.schemas import ArticleProviderError, ArticleRecord

logger = logging.getLogger(__name__)

GDELT_MAX_DAYS = 30


def _article_id(url: str) -> str:
    """Derive a stable article id from the URL (sha1 hex)."""
    return hashlib.sha1(url.strip().lower().encode("utf-8")).hexdigest()


def _parse_seen_date(raw: str | None) -> str | None:
    """Parse GDELT seendate format '2026 Sep 05 10:00:00' to ISO-8601 UTC."""
    if not raw:
        return None
    try:
        dt = datetime.strptime(str(raw).strip(), "%Y %b %d %H:%M:%S").replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except ValueError:
        return None


def _article_search_dataframe(query: str, start_date: str, end_date: str, limit: int):
    """Thin seam over gdeltdoc so tests can patch it without importing pandas."""
    from gdeltdoc import GdeltDoc, Filters

    filters = Filters(keyword=query, start_date=start_date, end_date=end_date)
    df = GdeltDoc().article_search(filters)
    if df is None or len(df) == 0:
        return []
    return df.head(limit)


def search(query: str, days: int, limit: int) -> list[ArticleRecord]:
    """Search GDELT for professional articles matching a query.

    :param query: Non-empty search keywords.
    :param days: Lookback window in days (capped at GDELT_MAX_DAYS).
    :param limit: Maximum records returned.
    :returns: List of normalized ArticleRecord values (newest-first from GDELT).
    :raises ValueError: When query is empty.
    :raises ArticleProviderError: When the GDELT call fails.
    """
    if not query or not query.strip():
        raise ValueError("query must be a non-empty string")

    effective_days = min(days, GDELT_MAX_DAYS)
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=effective_days)

    try:
        df = _article_search_dataframe(
            query.strip(),
            start.strftime("%Y-%m-%d"),
            end.strftime("%Y-%m-%d"),
            limit,
        )
    except Exception as exc:
        raise ArticleProviderError("gdelt", f"GDELT search failed: {exc}") from exc

    records: list[ArticleRecord] = []
    for row in df.to_dict(orient="records"):
        url = str(row.get("url") or "").strip()
        title = str(row.get("title") or "").strip()
        if not url.startswith(("http://", "https://")) or not title:
            continue
        domain = str(row.get("domain") or "").strip().lower() or (urlparse(url).netloc.lower() or None)
        records.append(
            ArticleRecord(
                article_id=_article_id(url),
                title=title,
                publisher=f"gdelt:{domain}" if domain else "gdelt",
                published_utc=_parse_seen_date(row.get("seendate")),
                url=url,
                summary=None,
                domain=domain,
                source="gdelt",
                access_status="ok",
            )
        )
        if len(records) >= limit:
            break
    return records
