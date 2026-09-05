"""ApeWisdom public API client for aggregate mention rankings.

Adapted from reference/reddit-trends/src/apewisdom.ts.
"""
from __future__ import annotations

import json
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Any
from app.social.schemas import SocialPost, SocialProviderError

DEFAULT_USER_AGENT = "MemeTradingResearchAgent/0.1 (ApeWisdom client)"
DEFAULT_TIMEOUT_SECONDS = 10


class ApeWisdomClient:
    """Client for querying ApeWisdom free public API."""

    def __init__(self, user_agent: str = DEFAULT_USER_AGENT, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> None:
        self.user_agent = user_agent
        self.timeout = timeout

    def _get_json(self, url: str) -> dict[str, Any]:
        """Fetch and parse JSON from a URL."""
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                if response.status != 200:
                    raise SocialProviderError("apewisdom", f"HTTP {response.status} from {url}")
                data = response.read().decode("utf-8")
                return json.loads(data)
        except Exception as exc:
            raise SocialProviderError("apewisdom", f"Failed to fetch ApeWisdom: {exc}") from exc

    def get_ticker_data(self, ticker: str, filter_slug: str = "all-stocks") -> tuple[SocialPost | None, float | None]:
        """Fetch rank and mention data for a ticker.

        Returns (SocialPost, mentions_24h_delta) or (None, None) if not found.
        """
        clean_ticker = ticker.upper().strip()
        url = f"https://apewisdom.io/api/v1.0/filter/{filter_slug}/page/1"
        try:
            data = self._get_json(url)
        except SocialProviderError:
            raise
        except Exception as exc:
            raise SocialProviderError("apewisdom", f"Failed to get ticker data: {exc}") from exc

        results = data.get("results", [])
        for item in results:
            item_ticker = str(item.get("ticker", "")).replace(".X", "").upper()
            if item_ticker == clean_ticker:
                mentions = int(item.get("mentions", 0))
                mentions_24h_ago = item.get("mentions_24h_ago")
                delta_24h = (mentions - int(mentions_24h_ago)) if mentions_24h_ago is not None else None
                upvotes = int(item.get("upvotes", 0))
                rank = item.get("rank")
                name = item.get("name", clean_ticker)

                now_utc = datetime.now(timezone.utc).isoformat()
                post = SocialPost(
                    post_id=f"apewisdom_{clean_ticker}",
                    source="apewisdom",
                    author=None,
                    created_utc=now_utc,
                    title=f"{name} (${clean_ticker}) ApeWisdom Rank {rank}",
                    text=f"ApeWisdom mentions: {mentions}, upvotes: {upvotes}, 24h mentions delta: {delta_24h}",
                    score=upvotes,
                    num_comments=mentions,
                    upvote_ratio=None,
                    url=f"https://apewisdom.io/stocks/{clean_ticker}/",
                    flair="AggregateMetrics",
                )
                return post, float(delta_24h) if delta_24h is not None else None

        return None, None
