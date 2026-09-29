"""DuckDuckGo and Tavily web-search provider.

Dual-provider search:
- Primary: Tavily AI Search (when TAVILY_API_KEY is configured). High-relevance,
  content-extracted snippets ideal for LLM ingestion and financial research.
- Fallback: DuckDuckGo via ddgs package (keyless).
"""
from __future__ import annotations

import logging
import os
from urllib.parse import urlparse

from app.websearch.schemas import WebRecord, WebSearchError

logger = logging.getLogger(__name__)

PROVIDER_NAME_DDG = "duckduckgo"
PROVIDER_NAME_TAVILY = "tavily"
PROVIDER_NAME = PROVIDER_NAME_DDG  # default / backwards-compatible alias


def _get_tavily_api_key() -> str | None:
    """Retrieve Tavily API key from environment, if present and non-empty."""
    key = os.environ.get("TAVILY_API_KEY", "").strip()
    return key or None


def _ddgs_text(query: str, limit: int) -> list[dict]:
    """Seam over ddgs so tests can patch without importing it."""
    from ddgs import DDGS

    with DDGS() as ddgs:
        return list(ddgs.text(query, max_results=limit))


def _tavily_request(api_key: str, query: str, limit: int, domains: list[str] | None = None) -> list[dict]:
    """Seam over Tavily REST API so tests can patch without live network requests."""
    import httpx

    payload: dict[str, object] = {
        "api_key": api_key,
        "query": query,
        "search_depth": "basic",
        "max_results": min(max(limit, 1), 20),
        "include_answer": False,
        "include_raw_content": False,
    }
    if domains:
        clean_domains = [d.strip() for d in domains if d and d.strip()]
        if clean_domains:
            payload["include_domains"] = clean_domains

    resp = httpx.post("https://api.tavily.com/search", json=payload, timeout=15.0)
    resp.raise_for_status()
    data = resp.json()
    return list(data.get("results", []))


def _domain_of(url: str) -> str:
    """Extract lowercase hostname from a URL."""
    try:
        return urlparse(url).netloc.lower()
    except ValueError:
        return ""


def _parse_ddg_rows(rows: list[dict], domains: list[str] | None = None, limit: int = 10) -> list[WebRecord]:
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


def _parse_tavily_rows(rows: list[dict], domains: list[str] | None = None, limit: int = 10) -> list[WebRecord]:
    allowed = {d.lower().strip() for d in domains} if domains else None
    records: list[WebRecord] = []
    seen: set[str] = set()
    for position, row in enumerate(rows):
        url = str(row.get("url") or "").strip()
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
                snippet=str(row.get("content") or "").strip() or None,
                position=position,
            )
        )
        if len(records) >= limit:
            break
    return records


def search_with_provider(query: str, domains: list[str] | None = None, limit: int = 10) -> tuple[list[WebRecord], str]:
    """Search using Tavily if configured, falling back to DuckDuckGo.

    :param query: Non-empty search keywords.
    :param domains: Optional domain allowlist.
    :param limit: Maximum results requested.
    :returns: Tuple of (deduplicated records, provider_name).
    :raises ValueError: On empty query.
    :raises WebSearchError: On total provider failure.
    """
    if not query or not query.strip():
        raise ValueError("query must be a non-empty string")

    clean_query = query.strip()
    tavily_key = _get_tavily_api_key()

    if tavily_key:
        try:
            rows = _tavily_request(tavily_key, clean_query, limit, domains)
            records = _parse_tavily_rows(rows, domains, limit)
            return records, PROVIDER_NAME_TAVILY
        except Exception as exc:
            logger.warning("Tavily search failed (%s: %s), falling back to DuckDuckGo", type(exc).__name__, exc)

    try:
        rows = _ddgs_text(clean_query, limit)
    except Exception as exc:
        raise WebSearchError(PROVIDER_NAME_DDG, f"search failed: {exc}") from exc

    records = _parse_ddg_rows(rows, domains, limit)
    return records, PROVIDER_NAME_DDG


def search(query: str, domains: list[str] | None = None, limit: int = 10) -> list[WebRecord]:
    """Search the general web for one query (backward-compatible signature)."""
    records, _ = search_with_provider(query, domains=domains, limit=limit)
    return records
