from unittest.mock import patch, MagicMock
import pytest
from app.social.search import search_social
from app.social.schemas import SocialPost, SocialSearchResult

def _mock_reddit_post(post_id: str, title: str, score: int) -> SocialPost:
    return SocialPost(
        post_id=post_id,
        source="reddit",
        author="analyst_joe",
        created_utc="2026-09-05T12:00:00Z",
        title=title,
        text="body",
        score=score,
        num_comments=10,
        upvote_ratio=0.9,
        url="https://reddit.com/r/stocks/1",
        flair="Discussion",
    )

def test_search_social_requires_query_or_ticker():
    with pytest.raises(ValueError, match="query or ticker"):
        search_social(query=None, ticker=None)

def test_search_social_ticker_query_orchestration():
    mock_reddit_posts = [
        _mock_reddit_post("reddit_1", "NVDA huge earnings", 100),
        _mock_reddit_post("reddit_2", "NVDA short squeeze thesis", 300),
    ]
    mock_ape_post = SocialPost(
        post_id="apewisdom_NVDA",
        source="apewisdom",
        author=None,
        created_utc="2026-09-05T12:00:00Z",
        title="NVIDIA ApeWisdom Rank 1",
        text="Mentions: 1500",
        score=4000,
        num_comments=1500,
        upvote_ratio=None,
        url="https://apewisdom.io/stocks/NVDA/",
        flair="AggregateMetrics",
    )

    mock_stocktwits_post = SocialPost(
        post_id="stocktwits_999",
        source="stocktwits",
        author="trader_bob",
        created_utc="2026-09-05T12:05:00Z",
        title="$NVDA on StockTwits: breaking resistance",
        text="$NVDA breaking resistance",
        score=25,
        num_comments=5,
        upvote_ratio=None,
        url="https://stocktwits.com/message/999",
        flair="Bullish",
    )

    with patch("app.social.search.RedditProvider") as MockReddit, \
         patch("app.social.search.ApeWisdomClient") as MockApe, \
         patch("app.social.search.StockTwitsClient") as MockST:
        
        mock_reddit_inst = MockReddit.return_value
        mock_reddit_inst.search.return_value = mock_reddit_posts
        
        mock_ape_inst = MockApe.return_value
        mock_ape_inst.get_ticker_data.return_value = (mock_ape_post, 350.0)

        mock_st_inst = MockST.return_value
        mock_st_inst.get_symbol_stream.return_value = [mock_stocktwits_post]

        res = search_social(ticker="NVDA", time_window="24h")

        assert isinstance(res, SocialSearchResult)
        assert res.ticker == "NVDA"
        assert res.time_window == "24h"
        assert res.metrics.total_mentions >= 1500  # from apewisdom aggregate
        assert res.metrics.mention_velocity_24h == 350.0
        assert res.source_summary.get("reddit") == 2
        assert res.source_summary.get("apewisdom") == 1
        assert res.source_summary.get("stocktwits") == 1
        assert len(res.representative_posts) > 0

def test_search_social_graceful_on_provider_failures():
    with patch("app.social.search.RedditProvider") as MockReddit, \
         patch("app.social.search.ApeWisdomClient") as MockApe, \
         patch("app.social.search.StockTwitsClient") as MockST:
        
        mock_reddit_inst = MockReddit.return_value
        mock_reddit_inst.search.side_effect = Exception("Reddit down")
        
        mock_ape_inst = MockApe.return_value
        mock_ape_inst.get_ticker_data.side_effect = Exception("ApeWisdom down")

        mock_st_inst = MockST.return_value
        mock_st_inst.get_symbol_stream.side_effect = Exception("StockTwits down")

        # Must not raise an unhandled crash; returns structured empty/degraded result
        res = search_social(ticker="UNKNOWN")
        assert res.ticker == "UNKNOWN"
        assert res.metrics.total_mentions == 0
        assert len(res.representative_posts) == 0
