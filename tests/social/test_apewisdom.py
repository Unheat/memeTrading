import json
from unittest.mock import patch, MagicMock
import pytest
from app.social.providers.apewisdom import ApeWisdomClient
from app.social.schemas import SocialProviderError

MOCK_APE_RESPONSE = {
    "count": 100,
    "pages": 1,
    "current_page": 1,
    "results": [
        {
            "rank": 1,
            "ticker": "NVDA",
            "name": "NVIDIA Corporation",
            "mentions": 1200,
            "upvotes": 4500,
            "rank_24h_ago": 3,
            "mentions_24h_ago": 800,
        },
        {
            "rank": 2,
            "ticker": "TSLA",
            "name": "Tesla Inc",
            "mentions": 900,
            "upvotes": 3000,
            "rank_24h_ago": 2,
            "mentions_24h_ago": 950,
        },
    ],
}

def test_apewisdom_fetch_ticker_success():
    client = ApeWisdomClient()
    with patch.object(client, "_get_json", return_value=MOCK_APE_RESPONSE):
        post, delta = client.get_ticker_data("NVDA")
        assert post is not None
        assert post.post_id == "apewisdom_NVDA"
        assert post.score == 4500
        assert post.num_comments == 1200
        assert delta == 400  # 1200 - 800

def test_apewisdom_fetch_ticker_not_found():
    client = ApeWisdomClient()
    with patch.object(client, "_get_json", return_value=MOCK_APE_RESPONSE):
        post, delta = client.get_ticker_data("GME")
        assert post is None
        assert delta is None

def test_apewisdom_network_failure_raises_provider_error():
    client = ApeWisdomClient()
    with patch.object(client, "_get_json", side_effect=Exception("Connection timed out")):
        with pytest.raises(SocialProviderError) as exc_info:
            client.get_ticker_data("NVDA")
        assert exc_info.value.provider == "apewisdom"
        assert exc_info.value.recoverable is True
