"""Tests for Apify Twitter/X keyed provider and search_social integration."""
from unittest.mock import patch
import pytest
from app.social.providers.apify_twitter import ApifyTwitterClient, API_TOKEN_ENV
from app.social.schemas import SocialPost, SocialProviderError

MOCK_DATASET_ITEMS = [
    {
        "id": "1700001",
        "text": "$MU DDR5 pricing going vertical. Suppliers sold out into Q1.",
        "createdAt": "2026-09-05T14:30:00.000Z",
        "author": {"userName": "supply_chain_sam"},
        "favoriteCount": 210,
        "replyCount": 34,
        "url": "https://x.com/supply_chain_sam/status/1700001",
    },
    {
        "id": "1700002",
        "text": "Called 5 distributors today, everyone quoting 12-week lead times on $MU memory.",
        "createdAt": "2026-09-05T15:10:00.000Z",
        "author": {"userName": "hardware_hank"},
        "favoriteCount": 88,
        "replyCount": 12,
        "url": "https://x.com/hardware_hank/status/1700002",
    },
]


def test_apify_unconfigured_returns_empty_silently():
    with patch.dict("os.environ", {}, clear=True):
        client = ApifyTwitterClient()
        assert client.is_configured is False
        assert client.search("$MU", limit=10) == []


def test_apify_search_maps_tweets():
    with patch.dict("os.environ", {API_TOKEN_ENV: "tok"}):
        client = ApifyTwitterClient()
        with patch.object(client, "_run_actor", return_value=MOCK_DATASET_ITEMS):
            posts = client.search("$MU", limit=10)
    assert len(posts) == 2
    assert all(isinstance(p, SocialPost) for p in posts)
    assert all(p.source == "twitter" for p in posts)
    p1 = posts[0]
    assert p1.post_id == "twitter_1700001"
    assert p1.author == "supply_chain_sam"
    assert p1.score == 210
    assert p1.num_comments == 34
    assert "DDR5" in p1.text
    assert p1.url.startswith("https://x.com/")


def test_apify_failure_raises_provider_error():
    with patch.dict("os.environ", {API_TOKEN_ENV: "tok"}):
        client = ApifyTwitterClient()
        with patch.object(client, "_run_actor", side_effect=Exception("HTTP 402")):
            with pytest.raises(SocialProviderError) as exc_info:
                client.search("$MU")
    assert exc_info.value.provider == "apify"


def test_search_social_includes_twitter_when_configured():
    from app.social.search import search_social

    mock_tweet = SocialPost(
        post_id="twitter_1700001", source="twitter", author="sam",
        created_utc="2026-09-05T14:30:00Z", title="$MU tweet", text="text",
        score=10, num_comments=2, upvote_ratio=None,
        url="https://x.com/s/status/1", flair=None,
    )
    with patch("app.social.search.RedditProvider") as MockReddit, \
         patch("app.social.search.ApeWisdomClient") as MockApe, \
         patch("app.social.search.StockTwitsClient") as MockST, \
         patch("app.social.search.ApifyTwitterClient") as MockApify:
        MockReddit.return_value.search.return_value = []
        MockApe.return_value.get_ticker_data.return_value = (None, None)
        MockST.return_value.get_symbol_stream.return_value = []
        MockApify.return_value.is_configured = True
        MockApify.return_value.search.return_value = [mock_tweet]

        res = search_social(ticker="MU")
    assert res.source_summary.get("twitter") == 1


def test_search_social_skips_twitter_when_unconfigured():
    from app.social.search import search_social

    with patch("app.social.search.RedditProvider") as MockReddit, \
         patch("app.social.search.ApeWisdomClient") as MockApe, \
         patch("app.social.search.StockTwitsClient") as MockST, \
         patch("app.social.search.ApifyTwitterClient") as MockApify:
        MockReddit.return_value.search.return_value = []
        MockApe.return_value.get_ticker_data.return_value = (None, None)
        MockST.return_value.get_symbol_stream.return_value = []
        MockApify.return_value.is_configured = False

        res = search_social(ticker="MU")
    assert "twitter" not in res.source_summary
