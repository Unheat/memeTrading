"""StockTwits public stream adapter for retail cashtag sentiment.

Donor provenance: adapted from reference/stock-market-intelligence/backend/app/adapters/sentiment_live.py:51-125
(StockTwitsSentimentProvider). Retains unauthenticated symbol stream endpoint, null-body rate-limit guard,
and 'entities: null' safe navigation workaround. Maps stream messages to normalized SocialPost records.
"""
from __future__ import annotations

import json
import logging
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Any
from app.social.schemas import SocialPost, SocialProviderError

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = "MemeTradingResearchAgent/0.1 (StockTwits client)"
DEFAULT_TIMEOUT_SECONDS = 10


def _parse_iso_utc(date_str: str | None) -> str:
    """Normalize date string to ISO-8601 UTC."""
    if not date_str:
        return datetime.now(timezone.utc).isoformat()
    try:
        # StockTwits timestamps are often ISO formatted e.g. "2026-09-05T14:30:00Z"
        # or RFC 2822
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError):
        return datetime.now(timezone.utc).isoformat()


class StockTwitsClient:
    """Client for querying StockTwits public symbol stream API without credentials."""

    def __init__(
        self,
        user_agent: str = DEFAULT_USER_AGENT,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.user_agent = user_agent
        self.timeout = timeout

    def _get_json(self, url: str) -> dict[str, Any] | None:
        """Fetch and parse JSON from StockTwits endpoint."""
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
                    raise SocialProviderError("stocktwits", f"HTTP {response.status} from {url}")
                data = response.read().decode("utf-8")
                parsed = json.loads(data)
                return parsed if isinstance(parsed, dict) else None
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                logger.warning("StockTwits rate limit exceeded (HTTP 429)")
                return None
            raise SocialProviderError("stocktwits", f"HTTP {exc.code} from {url}") from exc
        except Exception as exc:
            raise SocialProviderError("stocktwits", f"Failed to fetch StockTwits stream: {exc}") from exc

    def get_symbol_stream(self, ticker: str, limit: int = 30) -> list[SocialPost]:
        """Fetch latest cashtag stream messages for a ticker.

        :param ticker: Stock ticker symbol (e.g. "NVDA").
        :param limit: Maximum messages to return (default 30).
        :returns: List of normalized SocialPost records.
        """
        clean_ticker = ticker.upper().strip()
        url = f"https://api.stocktwits.com/api/2/streams/symbol/{clean_ticker}.json"

        try:
            data = self._get_json(url)
        except SocialProviderError:
            raise
        except Exception as exc:
            raise SocialProviderError("stocktwits", f"Error retrieving stream for {clean_ticker}: {exc}") from exc

        if not data or not isinstance(data, dict):
            return []

        raw_messages = data.get("messages") or []
        posts: list[SocialPost] = []

        for msg in raw_messages[:limit]:
            msg_id = msg.get("id")
            if not msg_id:
                continue

            body = str(msg.get("body") or "").strip()
            user = msg.get("user") or {}
            username = user.get("username")

            # Donor workaround: StockTwits sends "entities": null on untagged messages
            entities = msg.get("entities") or {}
            sentiment_obj = entities.get("sentiment") or {}
            sentiment_tag = sentiment_obj.get("basic")  # "Bullish" or "Bearish" or None

            likes_obj = msg.get("likes") or {}
            likes_count = max(0, int(likes_obj.get("total", 0)))

            convo_obj = msg.get("conversation") or {}
            replies = convo_obj.get("replies") or []
            comment_count = len(replies) if isinstance(replies, list) else 0

            created_utc = _parse_iso_utc(msg.get("created_at"))
            first_line = body.split("\n")[0][:60]
            title = f"${clean_ticker}: {first_line}..." if len(first_line) == 60 else f"${clean_ticker}: {first_line}"

            posts.append(
                SocialPost(
                    post_id=f"stocktwits_{msg_id}",
                    source="stocktwits",
                    author=username,
                    created_utc=created_utc,
                    title=title,
                    text=body,
                    score=likes_count,
                    num_comments=comment_count,
                    upvote_ratio=None,
                    url=f"https://stocktwits.com/message/{msg_id}",
                    flair=sentiment_tag,
                )
            )

        return posts
