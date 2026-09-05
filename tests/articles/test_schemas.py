"""Tests for app.articles.schemas contracts."""
import pytest
from app.articles.schemas import (
    ArticleRecord,
    ArticleContent,
    ArticleSearchResult,
    ArticleProviderError,
)


def _record(**overrides) -> ArticleRecord:
    base = dict(
        article_id="a1b2c3",
        title="NVDA lands new datacenter deal",
        publisher="cnbc",
        published_utc="2026-09-05T10:00:00Z",
        url="https://www.cnbc.com/2026/09/05/nvda-deal.html",
        summary="Nvidia signed a new deal.",
        domain="cnbc.com",
        source="rss",
        access_status="ok",
    )
    base.update(overrides)
    return ArticleRecord(**base)


def test_article_record_valid_and_frozen():
    rec = _record()
    assert rec.source == "rss"
    with pytest.raises(Exception):
        rec.title = "mutated"


def test_article_record_rejects_bad_url():
    with pytest.raises(ValueError, match="url"):
        _record(url="not-a-url")
    with pytest.raises(ValueError, match="url"):
        _record(url="ftp://example.com/x")


def test_article_record_rejects_bad_status_and_source():
    with pytest.raises(ValueError, match="source"):
        _record(source="twitter")
    with pytest.raises(ValueError, match="access_status"):
        _record(access_status="partially")


def test_article_record_serialization_round_trip():
    rec = _record(published_utc=None, summary=None, domain=None)
    d = rec.to_dict()
    assert d["published_utc"] is None
    restored = ArticleRecord.from_dict(d)
    assert restored == rec


def test_article_content_requires_text_when_ok():
    content = ArticleContent(
        url="https://www.cnbc.com/x.html",
        title="Title",
        text="Body text long enough.",
        author="Jane Doe",
        published_utc="2026-09-05T10:00:00Z",
        site_name="CNBC",
        status="ok",
        extraction_note=None,
    )
    d = content.to_dict()
    assert d["status"] == "ok"
    assert ArticleContent.from_dict(d) == content

    with pytest.raises(ValueError, match="text"):
        ArticleContent(
            url="https://www.cnbc.com/x.html",
            title="Title",
            text="",
            author=None,
            published_utc=None,
            site_name=None,
            status="ok",
            extraction_note=None,
        )


def test_article_content_failed_statuses_allow_empty_text():
    for status in ("paywalled", "unavailable", "extraction_failed"):
        content = ArticleContent(
            url="https://www.wsj.com/x.html",
            title="Title",
            text="",
            author=None,
            published_utc=None,
            site_name=None,
            status=status,
            extraction_note="blocked",
        )
        assert content.text == ""


def test_article_search_result_unique_urls_enforced():
    r1 = _record(article_id="1")
    r2 = _record(article_id="2")  # same url as r1
    metrics = None
    with pytest.raises(ValueError, match="unique"):
        ArticleSearchResult(
            query="nvda",
            ticker="NVDA",
            days=7,
            records=(r1, r2),
            source_summary={"rss": 2},
        )


def test_article_search_result_round_trip():
    r1 = _record()
    result = ArticleSearchResult(
        query="nvda",
        ticker="NVDA",
        days=7,
        records=(r1,),
        source_summary={"rss": 1},
    )
    d = result.to_dict()
    restored = ArticleSearchResult.from_dict(d)
    assert restored == result


def test_article_provider_error_format():
    err = ArticleProviderError("gdelt", "HTTP 503", recoverable=True)
    assert str(err) == "[gdelt] HTTP 503 (recoverable=True)"
    assert err.recoverable is True
