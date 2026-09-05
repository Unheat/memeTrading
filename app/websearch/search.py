"""Outer-agent general web search orchestrator: search_web tool."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.websearch.provider import PROVIDER_NAME, search as provider_search
from app.websearch.schemas import WebSearchResult

logger = logging.getLogger(__name__)


def search_web(query: str, domains: list[str] | None = None, limit: int = 10) -> WebSearchResult:
    """Search the general web for company/counterparty/IR/press-release sources.

    :param query: Non-empty search keywords.
    :param domains: Optional domain allowlist.
    :param limit: Maximum results (positive).
    :returns: WebSearchResult with deduplicated HTTPS records and provenance.
    :raises ValueError: On invalid query or limit.
    """
    if not query or not query.strip():
        raise ValueError("query must be a non-empty string")
    if limit <= 0:
        raise ValueError("limit must be positive")

    clean_query = query.strip()
    records = provider_search(clean_query, domains=domains, limit=limit)

    return WebSearchResult(
        query=clean_query,
        domains=tuple(domains) if domains else None,
        records=tuple(records),
        provider=PROVIDER_NAME,
        as_of=datetime.now(timezone.utc).isoformat(),
    )
