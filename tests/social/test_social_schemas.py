import pytest
from app.social.schemas import SocialPost, TrendMetrics, SocialSearchResult, SocialProviderError

def test_social_post_valid_and_frozen():
    post = SocialPost(
        post_id="reddit_123",
        source="reddit",
        author="trader42",
        created_utc="2026-09-05T12:00:00Z",
        title="NVDA partnership rumor",
        text="Check out this new filing!",
        score=150,
        num_comments=45,
        upvote_ratio=0.92,
        url="https://reddit.com/r/stocks/123",
        flair="Discussion",
    )
    assert post.post_id == "reddit_123"
    assert post.score == 150
    assert post.upvote_ratio == 0.92
    
    with pytest.raises(Exception):
        post.score = 200  # must be frozen

def test_social_post_serialization_round_trip():
    post = SocialPost(
        post_id="ape_nvda",
        source="apewisdom",
        author=None,
        created_utc="2026-09-05T10:00:00Z",
        title="NVIDIA",
        text="ApeWisdom Rank 1",
        score=500,
        num_comments=100,
        upvote_ratio=None,
        url="https://apewisdom.io/stocks/NVDA/",
        flair=None,
    )
    d = post.to_dict()
    assert d["author"] is None
    assert d["score"] == 500
    
    restored = SocialPost.from_dict(d)
    assert restored == post

def test_social_post_validation_errors():
    with pytest.raises(ValueError, match="post_id"):
        SocialPost(
            post_id="",
            source="reddit",
            author=None,
            created_utc="2026-09-05T12:00:00Z",
            title="Title",
            text="Text",
            score=0,
            num_comments=0,
            upvote_ratio=None,
            url="https://reddit.com",
            flair=None,
        )
    with pytest.raises(ValueError, match="score"):
        SocialPost(
            post_id="1",
            source="reddit",
            author=None,
            created_utc="2026-09-05T12:00:00Z",
            title="Title",
            text="Text",
            score=-1,
            num_comments=0,
            upvote_ratio=None,
            url="https://reddit.com",
            flair=None,
        )

def test_trend_metrics_valid_and_serialization():
    metrics = TrendMetrics(
        total_mentions=450,
        mention_velocity_24h=120.5,
        baseline_mentions=200.0,
        z_score=3.2,
        unique_author_ratio=0.75,
        engagement_acceleration=1.8,
        is_spike=True,
    )
    d = metrics.to_dict()
    assert d["is_spike"] is True
    assert d["z_score"] == 3.2
    restored = TrendMetrics.from_dict(d)
    assert restored == metrics

def test_social_search_result_round_trip():
    post = SocialPost(
        post_id="reddit_1",
        source="reddit",
        author="user1",
        created_utc="2026-09-05T12:00:00Z",
        title="Post 1",
        text="Some text",
        score=10,
        num_comments=2,
        upvote_ratio=0.8,
        url="https://reddit.com/1",
        flair=None,
    )
    metrics = TrendMetrics(
        total_mentions=10,
        mention_velocity_24h=5.0,
        baseline_mentions=5.0,
        z_score=1.5,
        unique_author_ratio=0.9,
        engagement_acceleration=1.0,
        is_spike=False,
    )
    result = SocialSearchResult(
        query="NVDA",
        ticker="NVDA",
        time_window="24h",
        metrics=metrics,
        representative_posts=(post,),
        source_summary={"reddit": 1},
        as_of="2026-09-05T12:30:00Z",
    )
    assert result.ticker == "NVDA"
    assert len(result.representative_posts) == 1
    
    d = result.to_dict()
    restored = SocialSearchResult.from_dict(d)
    assert restored == result

def test_social_provider_error():
    err = SocialProviderError("reddit", "Rate limit exceeded", recoverable=True)
    assert str(err) == "[reddit] Rate limit exceeded (recoverable=True)"
    assert err.provider == "reddit"
    assert err.recoverable is True
