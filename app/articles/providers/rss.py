"""RSS article provider adapted from finnews donor feed registries.

Donor provenance: feed URL templates and topic ids adapted from
reference/finance-news-aggregator/finnews/{wsj,cnbc,market_watch,nasdaq,yahoo_finance}.py
and finnews/fields.py. Parsing uses feedparser instead of the donor's
requests+defusedxml parser; entries are normalized into ArticleRecord.
"""
from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import feedparser

from app.articles.schemas import ArticleRecord

logger = logging.getLogger(__name__)

# Publisher -> list of RSS feed URLs. Adapted from finnews donor adapters.
RSS_FEED_REGISTRY: dict[str, list[str]] = {
    "wsj": [
        "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
        "https://feeds.a.dj.com/rss/rss_business.xml",
        "https://feeds.a.dj.com/rss/rsstechnology.xml",
    ],
    "cnbc": [
        "https://www.cnbc.com/id/100003114/device/rss/rss.html",  # top news
        "https://www.cnbc.com/id/10001147/device/rss/rss.html",   # business
        "https://www.cnbc.com/id/19854910/device/rss/rss.html",   # technology
        "https://www.cnbc.com/id/15839135/device/rss/rss.html",   # earnings
    ],
    "marketwatch": [
        "https://feeds.marketwatch.com/marketwatch/mw_topstories/",
        "https://feeds.marketwatch.com/marketwatch/mw_realtimeheadlines/",
        "https://feeds.marketwatch.com/marketwatch/mw_marketpulse/",
    ],
    "nasdaq": [
        "https://www.nasdaq.com/feed/rssoutbound",
    ],
    "yahoo_finance": [
        "https://finance.yahoo.com/news/rssindex",
    ],
}

# Publishers whose RSS exposes only headline/description (full text paywalled).
PAYWALLED_PUBLISHERS: frozenset[str] = frozenset({"wsj"})

# Cap on entries scanned per feed to bound work.
MAX_ENTRIES_PER_FEED = 100


def _article_id(url: str) -> str:
    """Derive a stable article id from the URL (sha1 hex)."""
    return hashlib.sha1(url.strip().lower().encode("utf-8")).hexdigest()


def _parse_published_utc(entry: dict) -> str | None:
    """Convert feedparser's published_parsed struct to ISO-8601 UTC, or None."""
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    try:
        dt = datetime(*parsed[:6], tzinfo=timezone.utc)
        return dt.isoformat()
    except (TypeError, ValueError):
        return None


def _entry_to_record(publisher: str, entry: dict) -> ArticleRecord | None:
    """Map one feedparser entry to an ArticleRecord; None when unusable."""
    title = (entry.get("title") or "").strip()
    url = (entry.get("link") or "").strip()
    if not title or not url.startswith(("http://", "https://")):
        return None

    domain = urlparse(url).netloc.lower() or None
    access_status = "metadata_only" if publisher in PAYWALLED_PUBLISHERS else "ok"
    summary = (entry.get("summary") or "").strip() or None

    return ArticleRecord(
        article_id=_article_id(url),
        title=title,
        publisher=publisher,
        published_utc=_parse_published_utc(entry),
        url=url,
        summary=summary,
        domain=domain,
        source="rss",
        access_status=access_status,
    )


def fetch_feeds(feed_urls: list[tuple[str, str]], days: int, limit: int) -> list[ArticleRecord]:
    """Fetch and normalize RSS entries from (publisher, url) pairs.

    A broken feed is skipped with a log entry, never raised.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    records: list[ArticleRecord] = []

    for publisher, url in feed_urls:
        try:
            parsed = feedparser.parse(url)
            entries = list(getattr(parsed, "entries", []))[:MAX_ENTRIES_PER_FEED]
        except Exception as exc:
            logger.warning("RSS feed fetch failed for %s (%s): %s", publisher, url, exc)
            continue

        for entry in entries:
            record = _entry_to_record(publisher, entry)
            if record is None:
                continue
            if record.published_utc is not None:
                try:
                    published = datetime.fromisoformat(record.published_utc)
                except ValueError:
                    published = None
                if published is not None and published < cutoff:
                    continue
            records.append(record)
            if len(records) >= limit:
                return records

    return records


def search_rss(sources: list[str] | None, days: int, limit: int) -> list[ArticleRecord]:
    """Search registry feeds, optionally restricted to given publisher names."""
    selected: list[tuple[str, str]] = []
    for publisher, urls in RSS_FEED_REGISTRY.items():
        if sources and publisher not in sources:
            continue
        selected.extend((publisher, url) for url in urls)
    if not selected:
        return []
    return fetch_feeds(selected, days=days, limit=limit)
