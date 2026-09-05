"""Tests for read_article (trafilatura extraction seam) and search_articles orchestrator."""
from unittest.mock import patch
import pytest
from app.articles.reader import read_article
from app.articles.search import search_articles
from app.articles.schemas import ArticleRecord, ArticleProviderError


def _record(url: str, title: str = "Title", publisher: str = "gdelt:x.com", published_utc: str | None = None, source: str = "gdelt") -> ArticleRecord:
    return ArticleRecord(
        article_id=title.lower().replace(" ", "-"),
        title=title,
        publisher=publisher,
        published_utc=published_utc,
        url=url,
        summary=None,
        domain="x.com",
        source=source,
        access_status="ok",
    )


def test_read_article_rejects_non_https():
    content = read_article("http://example.com/article")
    assert content.status == "unavailable"

    content = read_article("not-a-url")
    assert content.status == "unavailable"


def test_read_article_ok():
    fake = {
        "title": "Big NVDA story",
        "text": "Full article body text. " * 10,
        "author": "Jane Doe",
        "date": "2026-09-05",
        "sitename": "Reuters",
    }
    with patch("app.articles.reader._bare_extraction", return_value=fake):
        content = read_article("https://www.reuters.com/a")
    assert content.status == "ok"
    assert content.text == fake["text"]
    assert content.author == "Jane Doe"
    assert content.site_name == "Reuters"


def test_read_article_extraction_failed_on_empty_text():
    with patch("app.articles.reader._bare_extraction", return_value=None):
        content = read_article("https://www.reuters.com/a")
    assert content.status == "extraction_failed"
    assert content.text == ""
    assert content.extraction_note


def test_read_article_paywalled_on_teaser_text():
    # Paywalled pages typically yield a short teaser snippet, not full text.
    with patch("app.articles.reader._bare_extraction", return_value={"title": "t", "text": "short teaser", "author": None, "date": None, "sitename": None}):
        content = read_article("https://www.wsj.com/a")
    assert content.status == "paywalled"
    assert content.text == ""
    assert "paywall" in content.extraction_note.lower() or "short" in content.extraction_note.lower()


def test_read_article_network_failure():
    with patch("app.articles.reader._bare_extraction", side_effect=Exception("timeout")):
        content = read_article("https://www.reuters.com/a")
    assert content.status == "unavailable"
    assert content.text == ""


def test_search_articles_requires_query():
    with pytest.raises(ValueError):
        search_articles("")
    with pytest.raises(ValueError):
        search_articles("   ")


def test_search_articles_merges_and_dedupes():
    rss_records = [
        _record("https://www.cnbc.com/a.html", title="RSS story", publisher="cnbc", published_utc="2026-09-05T12:00:00Z", source="rss"),
        _record("https://www.cnbc.com/b.html", title="RSS story 2", publisher="cnbc", published_utc="2026-09-04T12:00:00Z", source="rss"),
    ]
    gdelt_records = [
        _record("https://www.cnbc.com/a.html", title="GDELT duplicate of RSS story", publisher="gdelt:cnbc.com", published_utc="2026-09-05T11:00:00Z"),
        _record("https://www.reuters.com/c.html", title="Reuters story", publisher="gdelt:reuters.com", published_utc="2026-09-05T13:00:00Z"),
    ]
    with patch("app.articles.search.gdelt_search", return_value=gdelt_records) as mock_gdelt, \
         patch("app.articles.search.search_rss", return_value=rss_records) as mock_rss:
        result = search_articles("nvda", days=7, limit=20)

    urls = [r.url for r in result.records]
    assert len(urls) == len(set(urls)) == 3
    # newest first: reuters 13:00, cnbc 12:00, cnbc 2026-09-04
    assert result.records[0].url == "https://www.reuters.com/c.html"
    assert result.records[1].url == "https://www.cnbc.com/a.html"
    # dedupe keeps the rss record for the duplicated URL (rss runs first)
    assert result.records[1].publisher == "cnbc"
    assert result.source_summary == {"gdelt": 1, "rss": 2}


def test_search_articles_degrades_when_provider_fails():
    with patch("app.articles.search.gdelt_search", side_effect=ArticleProviderError("gdelt", "HTTP 503")), \
         patch("app.articles.search.search_rss", return_value=[_record("https://www.cnbc.com/a.html", published_utc="2026-09-05T12:00:00Z", source="rss")]):
        result = search_articles("nvda", days=7, limit=20)
    assert len(result.records) == 1
    assert result.source_summary == {"rss": 1}


def test_search_articles_truncates_to_limit():
    records = [_record(f"https://x.com/{i}", title=f"T{i}", published_utc=f"2026-09-0{(i % 5) + 1}T12:00:00Z") for i in range(10)]
    with patch("app.articles.search.gdelt_search", return_value=records), \
         patch("app.articles.search.search_rss", return_value=[]):
        result = search_articles("nvda", days=7, limit=4)
    assert len(result.records) == 4
