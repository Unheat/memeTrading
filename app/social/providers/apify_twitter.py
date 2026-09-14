"""Apify Twitter/X keyed provider (hosted scraper actor).

Black-box dependency: Apify REST API (`run-sync-get-dataset-items`). No donor code.
Env key: APIFY_API_TOKEN. Unconfigured client returns empty results silently
(disabled, not an error) per the keyed-provider policy.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request
from datetime import datetime, timezone
from typing import Any

from app.social.schemas import SocialPost, SocialProviderError

logger = logging.getLogger(__name__)

API_TOKEN_ENV = "APIFY_API_TOKEN"
# apidojo/tweet-scraper: production hosted actor for keyword/cashtag tweet search.
ACTOR_ID = "apidojo~tweet-scraper"
DEFAULT_TIMEOUT_SECONDS = 60
MAX_SEARCH_LIMIT = 50


class ApifyTwitterClient:
    """Client for on-demand Twitter/X cashtag search through a hosted Apify actor."""

    def __init__(self, api_token: str | None = None) -> None:
        self.api_token = api_token or os.getenv(API_TOKEN_ENV, "").strip() or None

    @property
    def is_configured(self) -> bool:
        """True when an API token is available."""
        return bool(self.api_token)

    def _run_actor(self, query: str, limit: int) -> list[dict[str, Any]]:
        """Run the sync actor and return dataset items."""
        url = (
            f"https://api.apify.com/v2/acts/{ACTOR_ID}/run-sync-get-dataset-items"
            f"?token={self.api_key_param()}"
        )
        body = json.dumps({"searchTerms": [query], "tweetsLimit": limit}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
                items = json.loads(response.read().decode("utf-8"))
                return items if isinstance(items, list) else []
        except Exception as exc:
            raise SocialProviderError("apify", f"actor run failed: {exc}") from exc

    def api_key_param(self) -> str:
        """Return the raw token for URL embedding (caller guarantees configured)."""
        return self.api_token or ""

    def search(self, query: str, limit: int = 25) -> list[SocialPost]:
        """Search Twitter/X posts for one query (e.g. "$MU").

        :param query: Search terms, cashtags included.
        :param limit: Maximum tweets requested (capped at MAX_SEARCH_LIMIT).
        :returns: Normalized SocialPost list with source="twitter"; empty when
                  the provider is unconfigured (keyless mode).
        """
        if not self.is_configured:
            return []
        clean_query = (query or "").strip()
        if not clean_query:
            raise ValueError("query must be a non-empty string")
        effective_limit = max(1, min(limit, MAX_SEARCH_LIMIT))

        try:
            items = self._run_actor(clean_query, effective_limit)
        except SocialProviderError:
            raise
        except Exception as exc:
            raise SocialProviderError("apify", f"tweet search failed: {exc}") from exc
        posts: list[SocialPost] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            tweet_id = item.get("id")
            text = str(item.get("text") or "").strip()
            if not tweet_id or not text:
                continue
            author = (item.get("author") or {}).get("userName")
            posts.append(
                SocialPost(
                    post_id=f"twitter_{tweet_id}",
                    source="twitter",
                    author=author,
                    created_utc=_normalize_created(item.get("createdAt")),
                    title=text.split("\n")[0][:60],
                    text=text,
                    score=max(0, int(item.get("favoriteCount") or 0)),
                    num_comments=max(0, int(item.get("replyCount") or 0)),
                    upvote_ratio=None,
                    url=str(item.get("url") or f"https://x.com/{author or 'i'}/status/{tweet_id}"),
                    flair=None,
                )
            )
            if len(posts) >= effective_limit:
                break
        return posts


def _normalize_created(raw: Any) -> str:
    """Normalize tweet createdAt to ISO-8601 UTC; fall back to now."""
    now = datetime.now(timezone.utc).isoformat()
    if not raw:
        return now
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).isoformat()
    except ValueError:
        return now
