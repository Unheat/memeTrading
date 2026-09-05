"""Outer-agent social research tool orchestrator.

Implements the normalized tool contract:
search_social(query: str | None = None, ticker: str | None = None, time_window: str | None = None) -> SocialSearchResult
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from app.social.schemas import SocialPost, SocialSearchResult
from app.social.metrics import (
    deduplicate_posts,
    select_representative_posts,
    calculate_trend_metrics,
)
from app.social.providers.apewisdom import ApeWisdomClient
from app.social.providers.reddit import RedditProvider

logger = logging.getLogger(__name__)


def search_social(
    query: str | None = None,
    ticker: str | None = None,
    time_window: str | None = None,
) -> SocialSearchResult:
    """Search social media (Reddit, ApeWisdom) and return normalized trend metrics and representative posts.

    :param query: Optional free-text search term.
    :param ticker: Optional stock ticker symbol (e.g. "NVDA").
    :param time_window: Search time window ("24h", "7d", etc.), defaults to "24h".
    :returns: SocialSearchResult with calculated metrics and high-signal posts.
    :raises ValueError: If both query and ticker are omitted.
    """
    if not query and not ticker:
        raise ValueError("At least one of query or ticker must be provided")

    clean_ticker = ticker.upper().strip() if ticker else None
    search_term = clean_ticker or query
    window = time_window or "24h"
    now_utc = datetime.now(timezone.utc).isoformat()

    all_posts: list[SocialPost] = []
    source_summary: dict[str, int] = {}
    ape_mentions: int | None = None
    velocity_24h: float | None = None

    # 1. Query ApeWisdom if ticker is provided
    if clean_ticker:
        try:
            ape_client = ApeWisdomClient()
            ape_post, ape_delta = ape_client.get_ticker_data(clean_ticker)
            if ape_post:
                all_posts.append(ape_post)
                ape_mentions = ape_post.num_comments  # ApeWisdom mentions mapped to num_comments
                velocity_24h = ape_delta
                source_summary["apewisdom"] = 1
        except Exception as exc:
            logger.warning("ApeWisdom provider error during search_social: %s", exc)

    # 2. Query Reddit
    try:
        reddit_provider = RedditProvider()
        reddit_posts = reddit_provider.search(query=search_term or "", limit=25)
        if reddit_posts:
            all_posts.extend(reddit_posts)
            source_summary["reddit"] = len(reddit_posts)
    except Exception as exc:
        logger.warning("Reddit provider error during search_social: %s", exc)

    # 3. Deduplicate posts
    deduped = deduplicate_posts(all_posts)

    # 4. Calculate trend metrics
    # If ApeWisdom provided an aggregate mention count, use that for total_mentions
    total_mentions_override = ape_mentions if (ape_mentions is not None and ape_mentions > len(deduped)) else len(deduped)
    metrics = calculate_trend_metrics(
        posts=deduped,
        total_mentions_override=total_mentions_override,
        velocity_24h=velocity_24h,
    )

    # 5. Select high-signal representative posts
    representative = select_representative_posts(deduped, max_posts=4)

    return SocialSearchResult(
        query=query,
        ticker=clean_ticker,
        time_window=window,
        metrics=metrics,
        representative_posts=tuple(representative),
        source_summary=source_summary,
        as_of=now_utc,
    )
