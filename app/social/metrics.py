"""Deterministic statistical metrics and filtering for social intelligence."""
from __future__ import annotations

import re
import statistics
from typing import Sequence
from app.social.schemas import SocialPost, TrendMetrics

# Threshold for flagging an attention spike
Z_SCORE_SPIKE_THRESHOLD = 2.0
VELOCITY_SPIKE_PERCENT = 100.0


def calculate_unique_author_ratio(posts: Sequence[SocialPost]) -> float:
    """Calculate the ratio of distinct non-null authors to total posts.

    A ratio < 0.3 indicates coordinated spam or bot manipulation.
    """
    if not posts:
        return 1.0
    authors = {p.author for p in posts if p.author is not None}
    return round(len(authors) / len(posts), 4)


def calculate_z_score(current: float, history: Sequence[float]) -> float:
    """Calculate Z-score given current value and historical baseline samples.

    Returns 0.0 if variance is 0 or history has fewer than 2 samples.
    """
    if len(history) < 2:
        return 0.0
    mean_val = statistics.mean(history)
    stdev_val = statistics.stdev(history)
    if stdev_val == 0.0:
        return 0.0
    return round((current - mean_val) / stdev_val, 4)


def _normalize_title(title: str) -> str:
    """Normalize title for duplicate detection."""
    clean = re.sub(r"[^\w\s]", "", title.lower())
    return " ".join(clean.split())


def deduplicate_posts(posts: Sequence[SocialPost]) -> list[SocialPost]:
    """Deduplicate posts by normalized title, retaining the highest engagement post."""
    deduped: dict[str, SocialPost] = {}
    for post in posts:
        key = _normalize_title(post.title)
        if not key:
            key = post.post_id
        if key not in deduped:
            deduped[key] = post
        else:
            existing = deduped[key]
            existing_eng = existing.score + existing.num_comments
            post_eng = post.score + post.num_comments
            if post_eng > existing_eng:
                deduped[key] = post
    return list(deduped.values())


def select_representative_posts(
    posts: Sequence[SocialPost], max_posts: int = 4
) -> list[SocialPost]:
    """Select high-signal representative posts: top post plus representative quantile posts.

    Donor logic adapted from reference/reddit-stock-ai-agent-recommendation/stock_ai/reddit/post_scrape_filter.py.
    """
    if not posts:
        return []
    sorted_posts = sorted(posts, key=lambda p: (p.score, p.num_comments), reverse=True)
    if len(sorted_posts) <= max_posts:
        return sorted_posts

    # Always take the #1 highest-score post
    selected = [sorted_posts[0]]

    # Take candidate posts from the top 50% excluding #1
    top_half = sorted_posts[1 : len(sorted_posts) // 2 + 1]
    if top_half:
        # Pick the post with highest comment discussion in the top half
        by_comments = sorted(top_half, key=lambda p: p.num_comments, reverse=True)
        for post in by_comments:
            if post not in selected:
                selected.append(post)
                if len(selected) >= max_posts:
                    break

    # If still have room, fill from sorted
    for post in sorted_posts:
        if len(selected) >= max_posts:
            break
        if post not in selected:
            selected.append(post)

    return selected[:max_posts]


def calculate_trend_metrics(
    posts: Sequence[SocialPost],
    total_mentions_override: int | None = None,
    baseline_history: Sequence[float] | None = None,
    velocity_24h: float | None = None,
) -> TrendMetrics:
    """Calculate aggregated TrendMetrics across a set of posts and optional baseline data."""
    total_mentions = total_mentions_override if total_mentions_override is not None else len(posts)
    unique_author_ratio = calculate_unique_author_ratio(posts)

    baseline_mean = (
        statistics.mean(baseline_history)
        if (baseline_history and len(baseline_history) > 0)
        else None
    )

    z_score = None
    if baseline_history and len(baseline_history) >= 2:
        z_score = calculate_z_score(float(total_mentions), baseline_history)

    # Spike detection
    is_spike = False
    if z_score is not None and z_score >= Z_SCORE_SPIKE_THRESHOLD:
        is_spike = True
    elif velocity_24h is not None and velocity_24h >= VELOCITY_SPIKE_PERCENT:
        is_spike = True

    # Engagement acceleration (e.g. upvotes per comment or ratio)
    total_score = sum(p.score for p in posts)
    total_comments = sum(p.num_comments for p in posts)
    eng_accel = round(total_score / (total_comments + 1.0), 2) if posts else None

    return TrendMetrics(
        total_mentions=total_mentions,
        mention_velocity_24h=velocity_24h,
        baseline_mentions=round(baseline_mean, 2) if baseline_mean is not None else None,
        z_score=z_score,
        unique_author_ratio=unique_author_ratio,
        engagement_acceleration=eng_accel,
        is_spike=is_spike,
    )
