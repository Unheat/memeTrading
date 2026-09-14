"""Tests for Finnhub keyed provider and get_company_research fallback."""
import json
from unittest.mock import patch
import pytest
from app.market.providers.finnhub import FinnhubClient, API_KEY_ENV
from app.market.schemas import MarketDataError
from app.market.company_research import get_company_research


def _mock_get(path: str, params: dict):
    if path == "/stock/recommendation":
        return [{"strongBuy": 12, "buy": 20, "hold": 9, "sell": 2, "strongSell": 1, "period": "2026-09-01"}]
    if path == "/stock/price-target":
        return {"targetHigh": 180.0, "targetLow": 90.0, "targetMean": 130.0, "targetMedian": 128.0, "lastUpdated": "2026-09-05"}
    if path == "/stock/insider-transactions":
        return {"data": [
            {"name": "SANJAY MEHROTRA", "transactionCode": "F", "share": 45000,
             "transactionPrice": 118.2, "change": -45000, "filedAt": "2026-09-01"},
            {"name": "CEO2", "transactionCode": "S", "share": 10000,
             "transactionPrice": 120.0, "change": -10000, "filedAt": "2026-08-28"},
        ]}
    return {}


def test_finnhub_unconfigured_is_disabled():
    with patch.dict("os.environ", {}, clear=True):
        client = FinnhubClient()
        assert client.is_configured is False
        assert client.get_recommendation_trends("MU") == []
        assert client.get_price_target("MU") is None
        assert client.get_insider_transactions("MU") == []


def test_finnhub_recommendation_and_price_target():
    with patch.dict("os.environ", {API_KEY_ENV: "test-key"}):
        client = FinnhubClient()
        with patch.object(client, "_get", side_effect=_mock_get):
            trends = client.get_recommendation_trends("MU")
            target = client.get_price_target("MU")
    assert trends[0]["buy"] == 20
    assert target["targetMean"] == 130.0


def test_finnhub_insider_transactions_mapped():
    with patch.dict("os.environ", {API_KEY_ENV: "test-key"}):
        client = FinnhubClient()
        with patch.object(client, "_get", side_effect=_mock_get):
            rows = client.get_insider_transactions("MU")
    assert len(rows) == 2
    assert rows[0]["transaction_code"] == "F"  # tax withholding, pre-parsed
    assert rows[0]["shares"] == 45000
    assert rows[0]["filed_at"] == "2026-09-01"


def test_finnhub_api_failure_raises_market_error():
    with patch.dict("os.environ", {API_KEY_ENV: "test-key"}):
        client = FinnhubClient()
        with patch.object(client, "_get", side_effect=Exception("429")):
            with pytest.raises(MarketDataError):
                client.get_recommendation_trends("MU")


def test_company_research_finnhub_fallback_fills_empty_sections():
    """yfinance returns nothing; Finnhub key present -> sections filled with finnhub provenance."""
    with patch.dict("os.environ", {API_KEY_ENV: "test-key"}):
        with patch("app.market.company_research._yf_price_targets", return_value={}), \
             patch("app.market.company_research._yf_recommendations", return_value=None), \
             patch("app.market.company_research._yf_estimates", return_value={}), \
             patch("app.market.company_research._yf_calendar", return_value={}), \
             patch("app.market.company_research.FinnhubClient") as MockFh:
            inst = MockFh.return_value
            inst.is_configured = True
            inst.get_price_target.return_value = {"targetHigh": 180.0, "targetLow": 90.0, "targetMean": 130.0}
            inst.get_recommendation_trends.return_value = [
                {"strongBuy": 12, "buy": 20, "hold": 9, "sell": 2, "strongSell": 1}
            ]
            result = get_company_research("MU")

    assert result.price_targets is not None
    assert result.price_targets.mean.value == 130.0
    assert result.price_targets.mean.provider == "finnhub"
    assert result.ratings is not None
    assert result.ratings.buy == 20
    assert result.ratings.provider == "finnhub"


def test_company_research_finnhub_unconfigured_leaves_unavailable():
    with patch.dict("os.environ", {}, clear=True):
        with patch("app.market.company_research._yf_price_targets", return_value={}), \
             patch("app.market.company_research._yf_recommendations", return_value=None), \
             patch("app.market.company_research._yf_estimates", return_value={}), \
             patch("app.market.company_research._yf_calendar", return_value={}):
            result = get_company_research("SKETCHY")
    assert result.price_targets is None
    assert result.ratings is None
