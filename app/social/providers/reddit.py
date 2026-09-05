"""Reddit post provider using PRAW with graceful fallback.

Adapted from reference/reddit-stock-ai-agent-recommendation/stock_ai/reddit/reddit_scraper.py.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Sequence
from app.social.schemas import SocialPost, SocialProviderError

DEFAULT_SUBREDDITS = ("wallstreetbets", "stocks", "investing", "pennystocks")


class RedditProvider:
    """Provider for scraping/searching Reddit submissions via PRAW or mock."""

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        self.client_id = client_id or os.getenv("REDDIT_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("REDDIT_CLIENT_SECRET")
        self.user_agent = user_agent or os.getenv("REDDIT_USER_AGENT", "MemeTradingAgent/0.1")

    @property
    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.user_agent)

    def _fetch_submissions(self, query: str, limit: int = 25) -> Sequence[Any]:
        """Call PRAW search across subreddits."""
        try:
            import praw
        except ImportError:
            raise SocialProviderError("reddit", "praw package is not installed", recoverable=True)

        try:
            reddit = praw.Reddit(
                client_id=self.client_id,
                client_secret=self.client_secret,
                user_agent=self.user_agent,
            )
            # Search combined subreddits
            sub_combo = "+".join(DEFAULT_SUBREDDITS)
            subreddit = reddit.subreddit(sub_combo)
            return list(subreddit.search(query, limit=limit, sort="relevance", time_filter="week"))
        except Exception as exc:
            raise SocialProviderError("reddit", f"PRAW search failed: {exc}", recoverable=True) from exc

    def search(self, query: str, limit: int = 25) -> list[SocialPost]:
        """Search subreddits for query and map results to SocialPost."""
        if not self.is_configured:
            return []

        submissions = self._fetch_submissions(query, limit=limit)
        posts: list[SocialPost] = []
        for sub in submissions:
            created_dt = datetime.fromtimestamp(sub.created_utc, tz=timezone.utc)
            author_name = getattr(sub.author, "name", None) if sub.author else None
            permalink = getattr(sub, "permalink", f"/comments/{sub.id}")
            url = permalink if permalink.startswith("http") else f"https://reddit.com{permalink}"

            posts.append(
                SocialPost(
                    post_id=f"reddit_{sub.id}",
                    source="reddit",
                    author=author_name,
                    created_utc=created_dt.isoformat(),
                    title=sub.title,
                    text=getattr(sub, "selftext", ""),
                    score=max(0, int(getattr(sub, "score", 0))),
                    num_comments=max(0, int(getattr(sub, "num_comments", 0))),
                    upvote_ratio=getattr(sub, "upvote_ratio", None),
                    url=url,
                    flair=getattr(sub, "link_flair_text", None),
                )
            )
        return posts
