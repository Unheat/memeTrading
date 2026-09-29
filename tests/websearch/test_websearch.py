"""Tests for search_web tool: schemas, DDG provider seam, orchestrator."""
from unittest.mock import patch
import pytest
from app.websearch.schemas import WebRecord, WebSearchResult, WebSearchError
from app.websearch.provider import search as ddg_search
from app.websearch.search import search_web


def _ddg_row(title="NVDA press release", href="https://ir.nvidia.com/pr", body="Company announces.") -> dict:
    return {"title": title, "href": href, "body": body}


@pytest.fixture(autouse=True)
def _isolate_search_env(monkeypatch):
    """Ensure baseline websearch tests run isolated from ambient TAVILY_API_KEY in .env."""
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)



def test_web_record_rejects_non_https():
    with pytest.raises(ValueError, match="url"):
        WebRecord(title="t", url="http://insecure.com/x", domain="insecure.com", snippet=None, position=0)


def test_web_search_result_round_trip():
    rec = WebRecord(title="Press release", url="https://ir.nvidia.com/pr",
                    domain="ir.nvidia.com", snippet="Company announces.", position=0)
    result = WebSearchResult(
        query="NVDA press release", domains=("ir.nvidia.com",),
        records=(rec,), provider="duckduckgo", as_of="2026-09-05T20:00:00Z",
    )
    d = result.to_dict()
    assert WebSearchResult.from_dict(d) == result


def test_ddg_search_maps_rows_and_filters_https():
    rows = [
        _ddg_row(),
        _ddg_row(title="Insecure", href="http://random.com/x", body="b"),
        _ddg_row(title="No url", href="", body="b"),
    ]
    with patch("app.websearch.provider._ddgs_text", return_value=rows):
        records = ddg_search("nvda press release", limit=10)
    assert [r.url for r in records] == ["https://ir.nvidia.com/pr"]
    assert records[0].domain == "ir.nvidia.com"


def test_ddg_search_domain_restriction():
    rows = [
        _ddg_row(href="https://ir.nvidia.com/pr"),
        _ddg_row(title="Other", href="https://random.com/x"),
    ]
    with patch("app.websearch.provider._ddgs_text", return_value=rows):
        records = ddg_search("nvda", domains=["ir.nvidia.com"], limit=10)
    assert len(records) == 1
    assert records[0].url == "https://ir.nvidia.com/pr"


def test_ddg_search_wraps_errors():
    with patch("app.websearch.provider._ddgs_text", side_effect=Exception("blocked")):
        with pytest.raises(WebSearchError) as exc_info:
            ddg_search("nvda", limit=10)
    assert exc_info.value.provider == "duckduckgo"


def test_search_web_orchestrator():
    rows = [_ddg_row(), _ddg_row(title="Dup", href="https://ir.nvidia.com/pr"), _ddg_row(title="Second", href="https://www.nvidia.com/news")]
    with patch("app.websearch.provider._ddgs_text", return_value=rows):
        result = search_web("NVDA announcement", limit=10)
    assert isinstance(result, WebSearchResult)
    urls = [r.url for r in result.records]
    assert len(urls) == len(set(urls)) == 2  # deduped
    assert result.provider == "duckduckgo"


def test_search_web_requires_query():
    with pytest.raises(ValueError):
        search_web("")
    with pytest.raises(ValueError):
        search_web("   ")


def _tavily_row(title="NVDA press release", url="https://ir.nvidia.com/pr", content="Company announces.") -> dict:
    return {"title": title, "url": url, "content": content}


def test_tavily_search_maps_rows_and_filters_https(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test-key")
    rows = [
        _tavily_row(),
        _tavily_row(title="Insecure", url="http://random.com/x", content="b"),
        _tavily_row(title="No url", url="", content="b"),
    ]
    with patch("app.websearch.provider._tavily_request", return_value=rows):
        records, provider = ddg_search.__globals__["search_with_provider"]("nvda press release", limit=10)
    assert [r.url for r in records] == ["https://ir.nvidia.com/pr"]
    assert records[0].domain == "ir.nvidia.com"
    assert records[0].snippet == "Company announces."
    assert provider == "tavily"


def test_tavily_search_domain_restriction(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test-key")
    rows = [
        _tavily_row(url="https://ir.nvidia.com/pr"),
        _tavily_row(title="Other", url="https://random.com/x"),
    ]
    with patch("app.websearch.provider._tavily_request", return_value=rows):
        records, provider = ddg_search.__globals__["search_with_provider"]("nvda", domains=["ir.nvidia.com"], limit=10)
    assert len(records) == 1
    assert records[0].url == "https://ir.nvidia.com/pr"
    assert provider == "tavily"


def test_tavily_search_fallback_to_ddg_on_error(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test-key")
    with patch("app.websearch.provider._tavily_request", side_effect=Exception("API rate limit")):
        with patch("app.websearch.provider._ddgs_text", return_value=[_ddg_row()]):
            records, provider = ddg_search.__globals__["search_with_provider"]("nvda", limit=10)
    assert provider == "duckduckgo"
    assert len(records) == 1
    assert records[0].url == "https://ir.nvidia.com/pr"


def test_search_web_orchestrator_records_tavily_provider(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test-key")
    rows = [_tavily_row()]
    with patch("app.websearch.provider._tavily_request", return_value=rows):
        result = search_web("NVDA announcement", limit=10)
    assert isinstance(result, WebSearchResult)
    assert result.provider == "tavily"
    assert result.records[0].snippet == "Company announces."

