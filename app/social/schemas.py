"""Schemas for social media intelligence and trend metrics."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class SocialPost:
    """Normalized social post from Reddit, ApeWisdom, or similar sources."""

    post_id: str
    source: str
    author: str | None
    created_utc: str
    title: str
    text: str
    score: int
    num_comments: int
    upvote_ratio: float | None
    url: str
    flair: str | None = None

    def __post_init__(self) -> None:
        if not self.post_id or not isinstance(self.post_id, str):
            raise ValueError("post_id must be a non-empty string")
        if not self.source or not isinstance(self.source, str):
            raise ValueError("source must be a non-empty string")
        if not self.created_utc or not isinstance(self.created_utc, str):
            raise ValueError("created_utc must be a non-empty string")
        if self.score < 0:
            raise ValueError("score must be non-negative")
        if self.num_comments < 0:
            raise ValueError("num_comments must be non-negative")
        if self.upvote_ratio is not None and not (0.0 <= self.upvote_ratio <= 1.0):
            raise ValueError("upvote_ratio must be between 0.0 and 1.0")

    def to_dict(self) -> dict[str, Any]:
        """Convert post to JSON-serializable dictionary."""
        return {
            "post_id": self.post_id,
            "source": self.source,
            "author": self.author,
            "created_utc": self.created_utc,
            "title": self.title,
            "text": self.text,
            "score": self.score,
            "num_comments": self.num_comments,
            "upvote_ratio": self.upvote_ratio,
            "url": self.url,
            "flair": self.flair,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SocialPost:
        """Create SocialPost from a dictionary."""
        return cls(
            post_id=str(data["post_id"]),
            source=str(data["source"]),
            author=str(data["author"]) if data.get("author") is not None else None,
            created_utc=str(data["created_utc"]),
            title=str(data.get("title", "")),
            text=str(data.get("text", "")),
            score=int(data.get("score", 0)),
            num_comments=int(data.get("num_comments", 0)),
            upvote_ratio=float(data["upvote_ratio"]) if data.get("upvote_ratio") is not None else None,
            url=str(data.get("url", "")),
            flair=str(data["flair"]) if data.get("flair") is not None else None,
        )


@dataclass(frozen=True)
class TrendMetrics:
    """Calculated statistical signals across social posts."""

    total_mentions: int
    mention_velocity_24h: float | None
    baseline_mentions: float | None
    z_score: float | None
    unique_author_ratio: float
    engagement_acceleration: float | None
    is_spike: bool

    def __post_init__(self) -> None:
        if self.total_mentions < 0:
            raise ValueError("total_mentions must be non-negative")
        if not (0.0 <= self.unique_author_ratio <= 1.0):
            raise ValueError("unique_author_ratio must be between 0.0 and 1.0")

    def to_dict(self) -> dict[str, Any]:
        """Convert TrendMetrics to a JSON-serializable dictionary."""
        return {
            "total_mentions": self.total_mentions,
            "mention_velocity_24h": self.mention_velocity_24h,
            "baseline_mentions": self.baseline_mentions,
            "z_score": self.z_score,
            "unique_author_ratio": self.unique_author_ratio,
            "engagement_acceleration": self.engagement_acceleration,
            "is_spike": self.is_spike,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> TrendMetrics:
        """Create TrendMetrics from a dictionary."""
        return cls(
            total_mentions=int(data.get("total_mentions", 0)),
            mention_velocity_24h=float(data["mention_velocity_24h"]) if data.get("mention_velocity_24h") is not None else None,
            baseline_mentions=float(data["baseline_mentions"]) if data.get("baseline_mentions") is not None else None,
            z_score=float(data["z_score"]) if data.get("z_score") is not None else None,
            unique_author_ratio=float(data.get("unique_author_ratio", 1.0)),
            engagement_acceleration=float(data["engagement_acceleration"]) if data.get("engagement_acceleration") is not None else None,
            is_spike=bool(data.get("is_spike", False)),
        )


@dataclass(frozen=True)
class SocialSearchResult:
    """Normalized response contract for the outer-agent search_social tool."""

    query: str | None
    ticker: str | None
    time_window: str
    metrics: TrendMetrics
    representative_posts: tuple[SocialPost, ...]
    source_summary: dict[str, int]
    as_of: str

    def to_dict(self) -> dict[str, Any]:
        """Convert SocialSearchResult to a JSON-serializable dictionary."""
        return {
            "query": self.query,
            "ticker": self.ticker,
            "time_window": self.time_window,
            "metrics": self.metrics.to_dict(),
            "representative_posts": [post.to_dict() for post in self.representative_posts],
            "source_summary": dict(self.source_summary),
            "as_of": self.as_of,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SocialSearchResult:
        """Create SocialSearchResult from a dictionary."""
        metrics = TrendMetrics.from_dict(data["metrics"])
        posts = tuple(SocialPost.from_dict(p) for p in data.get("representative_posts", []))
        return cls(
            query=str(data["query"]) if data.get("query") is not None else None,
            ticker=str(data["ticker"]) if data.get("ticker") is not None else None,
            time_window=str(data.get("time_window", "24h")),
            metrics=metrics,
            representative_posts=posts,
            source_summary=dict(data.get("source_summary", {})),
            as_of=str(data["as_of"]),
        )


class SocialProviderError(Exception):
    """Structured recoverable error for social providers."""

    def __init__(self, provider: str, message: str, recoverable: bool = True) -> None:
        super().__init__(f"[{provider}] {message} (recoverable={recoverable})")
        self.provider = provider
        self.message = message
        self.recoverable = recoverable
