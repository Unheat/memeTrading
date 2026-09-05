# Module Spec — `app/social/schemas.py`

## Responsibility

Define immutable, validated, JSON-serializable records for social research data, statistical indicators, and tool outputs.

## Public Contracts

### `SocialPost`
- `post_id: str`: Unique identifier (e.g., `reddit_123abc`).
- `source: str`: e.g. `"reddit"`, `"apewisdom"`.
- `author: str | None`: Author handle/ID or None if anonymous/unavailable.
- `created_utc: str`: ISO 8601 UTC timestamp.
- `title: str`: Headline or post title.
- `text: str`: Body text or summary.
- `score: int`: Upvotes / score (>= 0).
- `num_comments: int`: Comment count (>= 0).
- `upvote_ratio: float | None`: Upvote ratio between 0.0 and 1.0, or None.
- `url: str`: Canonical source URL.
- `flair: str | None`: Post flair or tag if present.

### `TrendMetrics`
- `total_mentions: int`: Count of mentions observed in sample or window (>= 0).
- `mention_velocity_24h: float | None`: Change or rate of mentions over 24h.
- `baseline_mentions: float | None`: Expected baseline mentions.
- `z_score: float | None`: Statistical deviation from baseline.
- `unique_author_ratio: float`: Fraction of distinct authors (0.0 to 1.0). If 0 posts, 1.0.
- `engagement_acceleration: float | None`: Rate of change in upvotes/comments or ratio to average.
- `is_spike: bool`: True if z_score exceeds threshold (default >= 2.0) or velocity > 100%.

### `SocialSearchResult`
- `query: str | None`: Search term if provided.
- `ticker: str | None`: Stock ticker (uppercase) if provided.
- `time_window: str`: e.g., `"24h"`, `"7d"`.
- `metrics: TrendMetrics`: Calculated statistical signals.
- `representative_posts: tuple[SocialPost, ...]`: Compact selection of top/representative posts.
- `source_summary: dict[str, int]`: Post counts per source (e.g. `{"reddit": 25, "apewisdom": 1}`).
- `as_of: str`: ISO 8601 UTC timestamp of calculation.

### `SocialProviderError`
Structured exception subclassing `Exception` with `provider: str`, `message: str`, `recoverable: bool`.

## Serialization Contract
Every public record provides `to_dict()` and `from_dict()`. Values are JSON-safe.
