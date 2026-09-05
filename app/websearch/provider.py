"""DuckDuckGo web-search provider.

Black-box dependency: ddgs package (no API key). No donor code exists for
general web search; this wraps the package's public API behind one seam.
"""
from __future__ import annotations

import logging
from urllib.parse import urlparse

from app.websearch.schemas import WebRecord, WebSearchError

logger = logging.getLogger(__name__)

PROVIDER_NAME = "duckduckgo"


def _ddgs_text(query: str, limit: int) -> list[dict]:
    """Seam over ddgs so tests can patch without importing it."""
    from ddgs import DDGS

    with DDGS() as ddgs:
        return list(ddgs.text(query, max_results=limit))


def _domain_of(url: str) -> str:
    """Extract lowercase hostname from a URL."""
    try:
        return urlparse(url).netloc.lower()
    except ValueError:
        return ""


def search(query: str, domains: list[str] | None = None, limit: int = 10) -> list[WebRecord]:
    """Search the general web for one query.

    :param query: Non-empty search keywords.
    :param domains: Optional domain allowlist (hostnames or bare domains).
    :param limit: Maximum results requested.
    :returns: Deduplicated HTTPS-only WebRecord list.
    :raises ValueError: On empty query.
    :raises WebSearchError: On provider failure.
    """
    if not query or not query.strip():
        raise ValueError("query must be a non-empty string")

    try:
        rows = _ddgs_text(query.strip(), limit)
    except Exception as exc:
        raise WebSearchError(PROVIDER_NAME, f"search failed: {exc}") from exc

    allowed = {d.lower().strip() for d in domains} if domains else None
    records: list[WebRecord] = []
    seen: set[str] = set()
    for position, row in enumerate(rows):
        url = str(row.get("href") or "").strip()
        title = str(row.get("title") or "").strip()
        if not title or not url.startswith("https://"):
            continue
        domain = _domain_of(url)
        if allowed and not any(domain == a or domain.endswith("." + a) for a in allowed):
            continue
        if url in seen:
            continue
        seen.add(url)
        records.append(
            WebRecord(
                title=title,
                url=url,
                domain=domain,
                snippet=str(row.get("body") or "").strip() or None,
                position=position,
            )
        )
        if len(records) >= limit:
            break
    return records
