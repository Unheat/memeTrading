"""Immutable records for general web search results."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlparse


def _is_https_url(url: str) -> bool:
    """Return True only for absolute HTTPS URLs."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme == "https" and bool(parsed.netloc)


@dataclass(frozen=True)
class WebRecord:
    """One normalized general-web search hit."""

    title: str
    url: str
    domain: str
    snippet: str | None
    position: int

    def __post_init__(self) -> None:
        if not self.title or not isinstance(self.title, str):
            raise ValueError("title must be a non-empty string")
        if not _is_https_url(self.url):
            raise ValueError("url must be an absolute HTTPS URL")
        if self.position < 0:
            raise ValueError("position must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        """Convert record to a JSON-serializable dictionary."""
        return {
            "title": self.title,
            "url": self.url,
            "domain": self.domain,
            "snippet": self.snippet,
            "position": self.position,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> WebRecord:
        """Rebuild record from its dictionary form, re-validating."""
        return cls(
            title=str(data["title"]),
            url=str(data["url"]),
            domain=str(data.get("domain", "")),
            snippet=str(data["snippet"]) if data.get("snippet") is not None else None,
            position=int(data.get("position", 0)),
        )


@dataclass(frozen=True)
class WebSearchResult:
    """Normalized response contract for the outer-agent search_web tool."""

    query: str
    domains: tuple[str, ...] | None
    records: tuple[WebRecord, ...]
    provider: str
    as_of: str

    def __post_init__(self) -> None:
        if not self.query or not isinstance(self.query, str):
            raise ValueError("query must be a non-empty string")
        urls = [r.url for r in self.records]
        if len(urls) != len(set(urls)):
            raise ValueError("records must have unique url values")

    def to_dict(self) -> dict[str, Any]:
        """Convert result to a JSON-serializable dictionary."""
        return {
            "query": self.query,
            "domains": list(self.domains) if self.domains else None,
            "records": [r.to_dict() for r in self.records],
            "provider": self.provider,
            "as_of": self.as_of,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> WebSearchResult:
        """Rebuild result from its dictionary form, re-validating."""
        records = tuple(WebRecord.from_dict(r) for r in data.get("records", []))
        domains = tuple(str(d) for d in data["domains"]) if data.get("domains") else None
        return cls(
            query=str(data["query"]),
            domains=domains,
            records=records,
            provider=str(data["provider"]),
            as_of=str(data["as_of"]),
        )


class WebSearchError(Exception):
    """Structured recoverable error for web-search providers."""

    def __init__(self, provider: str, message: str, recoverable: bool = True) -> None:
        super().__init__(f"[{provider}] {message} (recoverable={recoverable})")
        self.provider = provider
        self.message = message
        self.recoverable = recoverable
