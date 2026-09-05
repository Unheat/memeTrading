"""Immutable validated records for professional article search and extraction."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlparse

ALLOWED_SOURCES = ("rss", "gdelt")
ALLOWED_ACCESS_STATUSES = ("ok", "metadata_only", "paywalled", "unavailable")
ALLOWED_CONTENT_STATUSES = ("ok", "paywalled", "unavailable", "extraction_failed")


def _is_http_url(url: str) -> bool:
    """Return True only for absolute HTTP(S) URLs."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


@dataclass(frozen=True)
class ArticleRecord:
    """One normalized professional-article search hit."""

    article_id: str
    title: str
    publisher: str
    published_utc: str | None
    url: str
    summary: str | None
    domain: str | None
    source: str
    access_status: str

    def __post_init__(self) -> None:
        if not self.article_id or not isinstance(self.article_id, str):
            raise ValueError("article_id must be a non-empty string")
        if not self.title or not isinstance(self.title, str):
            raise ValueError("title must be a non-empty string")
        if not self.publisher or not isinstance(self.publisher, str):
            raise ValueError("publisher must be a non-empty string")
        if self.published_utc is not None and not isinstance(self.published_utc, str):
            raise ValueError("published_utc must be a string or None")
        if not _is_http_url(self.url):
            raise ValueError("url must be an absolute HTTP(S) URL")
        if self.summary is not None and not isinstance(self.summary, str):
            raise ValueError("summary must be a string or None")
        if self.source not in ALLOWED_SOURCES:
            raise ValueError(f"source must be one of {ALLOWED_SOURCES}")
        if self.access_status not in ALLOWED_ACCESS_STATUSES:
            raise ValueError(f"access_status must be one of {ALLOWED_ACCESS_STATUSES}")

    def to_dict(self) -> dict[str, Any]:
        """Convert record to a JSON-serializable dictionary."""
        return {
            "article_id": self.article_id,
            "title": self.title,
            "publisher": self.publisher,
            "published_utc": self.published_utc,
            "url": self.url,
            "summary": self.summary,
            "domain": self.domain,
            "source": self.source,
            "access_status": self.access_status,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ArticleRecord:
        """Rebuild a record from its dictionary form, re-validating all rules."""
        return cls(
            article_id=str(data["article_id"]),
            title=str(data["title"]),
            publisher=str(data["publisher"]),
            published_utc=str(data["published_utc"]) if data.get("published_utc") is not None else None,
            url=str(data["url"]),
            summary=str(data["summary"]) if data.get("summary") is not None else None,
            domain=str(data["domain"]) if data.get("domain") is not None else None,
            source=str(data["source"]),
            access_status=str(data["access_status"]),
        )


@dataclass(frozen=True)
class ArticleContent:
    """Extracted article text and metadata for one URL."""

    url: str
    title: str
    text: str
    author: str | None
    published_utc: str | None
    site_name: str | None
    status: str
    extraction_note: str | None

    def __post_init__(self) -> None:
        if not self.url or not isinstance(self.url, str):
            raise ValueError("url must be a non-empty string (echoed caller input)")
        if not self.title or not isinstance(self.title, str):
            raise ValueError("title must be a non-empty string")
        if self.status not in ALLOWED_CONTENT_STATUSES:
            raise ValueError(f"status must be one of {ALLOWED_CONTENT_STATUSES}")
        if self.status == "ok" and not self.text:
            raise ValueError("text must be non-empty when status is ok")
        if not isinstance(self.text, str):
            raise ValueError("text must be a string")

    def to_dict(self) -> dict[str, Any]:
        """Convert content to a JSON-serializable dictionary."""
        return {
            "url": self.url,
            "title": self.title,
            "text": self.text,
            "author": self.author,
            "published_utc": self.published_utc,
            "site_name": self.site_name,
            "status": self.status,
            "extraction_note": self.extraction_note,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ArticleContent:
        """Rebuild content from its dictionary form, re-validating all rules."""
        return cls(
            url=str(data["url"]),
            title=str(data["title"]),
            text=str(data.get("text", "")),
            author=str(data["author"]) if data.get("author") is not None else None,
            published_utc=str(data["published_utc"]) if data.get("published_utc") is not None else None,
            site_name=str(data["site_name"]) if data.get("site_name") is not None else None,
            status=str(data["status"]),
            extraction_note=str(data["extraction_note"]) if data.get("extraction_note") is not None else None,
        )


@dataclass(frozen=True)
class ArticleSearchResult:
    """Normalized response contract for the outer-agent search_articles tool."""

    query: str
    ticker: str | None
    days: int
    records: tuple[ArticleRecord, ...]
    source_summary: dict[str, int]

    def __post_init__(self) -> None:
        if not self.query or not isinstance(self.query, str):
            raise ValueError("query must be a non-empty string")
        if self.ticker is not None and (not self.ticker or not isinstance(self.ticker, str)):
            raise ValueError("ticker must be a non-empty string or None")
        if self.days <= 0:
            raise ValueError("days must be positive")
        urls = [r.url for r in self.records]
        if len(urls) != len(set(urls)):
            raise ValueError("records must have unique url values")
        if not isinstance(self.source_summary, dict):
            raise ValueError("source_summary must be a dict")

    def to_dict(self) -> dict[str, Any]:
        """Convert result to a JSON-serializable dictionary."""
        return {
            "query": self.query,
            "ticker": self.ticker,
            "days": self.days,
            "records": [r.to_dict() for r in self.records],
            "source_summary": dict(self.source_summary),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ArticleSearchResult:
        """Rebuild result from its dictionary form, re-validating all rules."""
        records = tuple(ArticleRecord.from_dict(r) for r in data.get("records", []))
        return cls(
            query=str(data["query"]),
            ticker=str(data["ticker"]) if data.get("ticker") is not None else None,
            days=int(data.get("days", 7)),
            records=records,
            source_summary=dict(data.get("source_summary", {})),
        )


class ArticleProviderError(Exception):
    """Structured recoverable error for article providers."""

    def __init__(self, provider: str, message: str, recoverable: bool = True) -> None:
        super().__init__(f"[{provider}] {message} (recoverable={recoverable})")
        self.provider = provider
        self.message = message
        self.recoverable = recoverable
