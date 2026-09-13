"""Tests for StockTwits social sentiment provider."""
from unittest.mock import patch
import pytest
from app.social.providers.stocktwits import StockTwitsClient
from app.social.schemas import SocialPost, SocialProviderError

MOCK_STOCKTWITS_RESPONSE = {
    "response": {"status": 200},
    "symbol": {"id": 8944, "symbol": "NVDA", "title": "NVIDIA Corp"},
    "messages": [
        {
            "id": 584910201,
            "body": "$NVDA massive volume breakout over 120 resistance! Going to 140 next week.",
            "created_at": "2026-09-05T14:30:00Z",
            "user": {
                "id": 123456,
                "username": "bullish_trader",
                "name": "Alex",
            },
            "entities": {
                "sentiment": {"basic": "Bullish"},
            },
            "likes": {"total": 15},
            "conversation": {"replies": [1, 2, 3]},
        },
        {
            "id": 584910202,
            "body": "$NVDA valuation is insane here, taking profits.",
            "created_at": "2026-09-05T14:32:00Z",
            "user": {
                "id": 654321,
                "username": "short_seller",
                "name": "Sam",
            },
            "entities": {
                "sentiment": {"basic": "Bearish"},
            },
            "likes": {"total": 4},
            "conversation": {"replies": []},
        },
        {
            # Donor edge case: "entities": null
            "id": 584910203,
            "body": "$NVDA anyone watching the options chain today?",
            "created_at": "2026-09-05T14:35:00Z",
            "user": {
                "id": 999999,
                "username": "options_watcher",
            },
            "entities": None,
            "likes": {"total": 0},
            "conversation": None,
        },
    ],
}


def test_stocktwits_fetch_stream_success():
    client = StockTwitsClient()
    with patch.object(client, "_get_json", return_value=MOCK_STOCKTWITS_RESPONSE):
        posts = client.get_symbol_stream("NVDA", limit=10)

    assert len(posts) == 3
    assert all(isinstance(p, SocialPost) for p in posts)
    assert all(p.source == "stocktwits" for p in posts)

    # Bullish post
    p1 = posts[0]
    assert p1.post_id == "stocktwits_584910201"
    assert p1.author == "bullish_trader"
    assert p1.flair == "Bullish"
    assert p1.score == 15
    assert p1.num_comments == 3
    assert "massive volume breakout" in p1.text
    assert p1.url == "https://stocktwits.com/message/584910201"

    # Bearish post
    p2 = posts[1]
    assert p2.author == "short_seller"
    assert p2.flair == "Bearish"

    # Untagged post with entities: None
    p3 = posts[2]
    assert p3.flair is None
    assert p3.score == 0
    assert p3.num_comments == 0


def test_stocktwits_null_or_invalid_response_handled_gracefully():
    client = StockTwitsClient()
    # When rate-limited or blocked, StockTwits returns non-dict or empty response
    with patch.object(client, "_get_json", return_value=None):
        posts = client.get_symbol_stream("NVDA")
        assert posts == []

    with patch.object(client, "_get_json", return_value={}):
        posts = client.get_symbol_stream("NVDA")
        assert posts == []


def test_stocktwits_provider_error_on_network_failure():
    client = StockTwitsClient()
    with patch.object(client, "_get_json", side_effect=Exception("HTTP 429 Too Many Requests")):
        with pytest.raises(SocialProviderError) as exc_info:
            client.get_symbol_stream("NVDA")
        assert exc_info.value.provider == "stocktwits"
        assert exc_info.value.recoverable is True
