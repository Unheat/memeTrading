"""Tests for RSS and GDELT article providers. All offline; fixtures + mocks."""
import time
from unittest.mock import patch, MagicMock
import pytest
from app.articles.providers.rss import (
    RSS_FEED_REGISTRY,
    PAYWALLED_PUBLISHERS,
    fetch_feeds,
    search_rss,
    _entry_to_record,
)
from app.articles.providers.gdelt import search as gdelt_search
from app.articles.schemas import ArticleProviderError


def _entry(title="NVDA beats earnings", link="https://www.cnbc.com/a.html", published=True, summary="Big quarter."):
    """Build a fake feedparser entry."""
    entry = {
        "title": title,
        "link": link,
        "summary": summary,
    }
    if published is not None:
        entry["published_parsed"] = time.struct_time((2026, 9, 5, 10, 0, 0, 5, 248, 0))
    return entry


def test_feed_registry_has_required_publishers():
    for publisher in ("wsj", "cnbc", "marketwatch", "nasdaq", "yahoo_finance"):
        assert publisher in RSS_FEED_REGISTRY
        assert RSS_FEED_REGISTRY[publisher], f"{publisher} must list feed URLs"
    assert "wsj" in PAYWALLED_PUBLISHERS


def test_entry_to_record_maps_fields():
    rec = _entry_to_record("cnbc", _entry())
    assert rec.title == "NVDA beats earnings"
    assert rec.url == "https://www.cnbc.com/a.html"
    assert rec.publisher == "cnbc"
    assert rec.source == "rss"
    assert rec.access_status == "ok"
    assert rec.summary == "Big quarter."
    assert rec.published_utc is not None


def test_entry_to_record_paywalled_publisher():
    rec = _entry_to_record("wsj", _entry(link="https://www.wsj.com/a.html"))
    assert rec.access_status == "metadata_only"


def test_fetch_feeds_skips_invalid_entries():
    feed = [_entry(), _entry(title="", link="https://x.com/b.html"), _entry(link="")]
    with patch("app.articles.providers.rss.feedparser.parse") as mock_parse:
        mock_parse.return_value = MagicMock(entries=feed)
        records = fetch_feeds([("cnbc", "https://feed.url/rss")], days=7, limit=20)
    assert len(records) == 1
    assert records[0].url == "https://www.cnbc.com/a.html"


def test_fetch_feeds_drops_stale_entries():
    # published 2026-09-05; days=1 should drop entries older than 1 day only if
    # they fall outside the window relative to "now" — fixture date is fixed, so
    # we assert the boundary logic with a very old date instead.
    old = dict(
        title="Old news",
        link="https://www.cnbc.com/old.html",
        summary="s",
        published_parsed=time.struct_time((2020, 1, 1, 0, 0, 0, 0, 1, 0)),
    )
    with patch("app.articles.providers.rss.feedparser.parse") as mock_parse:
        mock_parse.return_value = MagicMock(entries=[_entry(), old])
        records = fetch_feeds([("cnbc", "https://feed.url/rss")], days=7, limit=20)
    urls = [r.url for r in records]
    assert "https://www.cnbc.com/old.html" not in urls
    assert "https://www.cnbc.com/a.html" in urls


def test_fetch_feeds_skips_broken_feed():
    with patch("app.articles.providers.rss.feedparser.parse", side_effect=Exception("boom")):
        records = fetch_feeds([("cnbc", "https://feed.url/rss")], days=7, limit=20)
    assert records == []


def test_search_rss_filters_sources():
    with patch("app.articles.providers.rss.fetch_feeds", return_value=[]) as mock_fetch:
        search_rss(sources=["wsj"], days=7, limit=20)
        requested_publishers = {pub for pub, _ in mock_fetch.call_args[0][0]}
        assert requested_publishers == {"wsj"}


def _gdelt_df(rows):
    """Build a fake pandas DataFrame-like object."""
    import pandas as pd
    return pd.DataFrame(rows, columns=["url", "title", "seendate", "domain"])


def test_gdelt_search_maps_rows():
    df = _gdelt_df([
        ("https://www.reuters.com/a", "Reuters story", "2026 Sep 05 10:00:00", "reuters.com"),
        ("https://www.bloomberg.com/b", "Bloomberg story", "2026 Sep 04 09:00:00", "bloomberg.com"),
    ])
    with patch("app.articles.providers.gdelt._article_search_dataframe", return_value=df):
        records = gdelt_search("nvda partnership", days=7, limit=20)
    assert len(records) == 2
    assert records[0].source == "gdelt"
    assert records[0].publisher == "gdelt:reuters.com"
    assert records[0].title == "Reuters story"


def test_gdelt_search_wraps_errors():
    with patch("app.articles.providers.gdelt._article_search_dataframe", side_effect=Exception("HTTP 503")):
        with pytest.raises(ArticleProviderError) as exc_info:
            gdelt_search("nvda", days=7, limit=20)
        assert exc_info.value.provider == "gdelt"


def test_gdelt_search_rejects_empty_query():
    with pytest.raises(ValueError):
        gdelt_search("", days=7, limit=20)
