import pytest
from app.social.schemas import SocialPost
from app.social.metrics import (
    calculate_unique_author_ratio,
    calculate_z_score,
    deduplicate_posts,
    select_representative_posts,
    calculate_trend_metrics,
)

def _make_post(post_id: str, title: str, author: str | None, score: int, num_comments: int = 0) -> SocialPost:
    return SocialPost(
        post_id=post_id,
        source="reddit",
        author=author,
        created_utc="2026-09-05T12:00:00Z",
        title=title,
        text="text",
        score=score,
        num_comments=num_comments,
        upvote_ratio=0.9,
        url=f"https://reddit.com/{post_id}",
        flair="Discussion",
    )

def test_unique_author_ratio():
    posts = [
        _make_post("1", "t1", "alice", 10),
        _make_post("2", "t2", "alice", 20),
        _make_post("3", "t3", "bob", 30),
        _make_post("4", "t4", "charlie", 40),
    ]
    # 3 unique authors (alice, bob, charlie) across 4 posts = 0.75
    assert calculate_unique_author_ratio(posts) == 0.75

    # empty posts should return 1.0
    assert calculate_unique_author_ratio([]) == 1.0

    # all None authors
    none_posts = [_make_post("1", "t1", None, 10), _make_post("2", "t2", None, 20)]
    assert calculate_unique_author_ratio(none_posts) == 0.0

def test_calculate_z_score():
    # current=50, history=[10, 10, 10, 10] -> std is 0 -> 0.0
    assert calculate_z_score(50, [10, 10, 10]) == 0.0
    
    # history with mean 10, std approx 2.0
    # values: [8, 10, 12] -> mean=10, variance=4, std=2.0 (sample)
    # current=16 -> z = (16 - 10) / 2 = 3.0
    z = calculate_z_score(16, [8, 10, 12])
    assert pytest.approx(z, 0.01) == 3.0

    # empty or single history returns 0.0
    assert calculate_z_score(10, []) == 0.0
    assert calculate_z_score(10, [10]) == 0.0

def test_deduplicate_posts():
    posts = [
        _make_post("1", "Huge NVDA News!", "alice", 10, 5),
        _make_post("2", "huge nvda news!", "bob", 50, 20),  # duplicate title, higher score
        _make_post("3", "Different News", "charlie", 15, 2),
    ]
    deduped = deduplicate_posts(posts)
    assert len(deduped) == 2
    # Should keep post 2 because score is higher
    post_ids = [p.post_id for p in deduped]
    assert "2" in post_ids
    assert "1" not in post_ids
    assert "3" in post_ids

def test_select_representative_posts():
    posts = [
        _make_post("1", "Low score", "u1", 5, 1),
        _make_post("2", "Top score", "u2", 100, 50),
        _make_post("3", "Med score", "u3", 40, 15),
        _make_post("4", "Another med", "u4", 45, 10),
    ]
    selected = select_representative_posts(posts, max_posts=3)
    assert len(selected) <= 3
    # Top score must be included
    assert selected[0].post_id == "2"

def test_calculate_trend_metrics_spike_detection():
    posts = [
        _make_post("1", "p1", "u1", 10),
        _make_post("2", "p2", "u2", 20),
    ]
    # Current total 50, baseline 10, z_score 3.5 -> is_spike should be True
    metrics = calculate_trend_metrics(
        posts=posts,
        total_mentions_override=50,
        baseline_history=[10, 12, 8, 10],
        velocity_24h=150.0,
    )
    assert metrics.total_mentions == 50
    assert metrics.is_spike is True
    assert metrics.z_score is not None and metrics.z_score > 2.0
    assert metrics.unique_author_ratio == 1.0
