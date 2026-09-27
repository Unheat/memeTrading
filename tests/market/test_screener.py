"""Unit tests for quantitative equity screener provider."""
import json
from unittest.mock import MagicMock, patch
import pytest

from app.market.screener import (
    execute_equity_screen,
    normalize_sector,
    _format_quotes,
)
from app.agent.tools import create_agent_tools


def test_normalize_sector():
    """Sector normalization maps colloquial names to standard Yahoo Finance GICS sectors."""
    assert normalize_sector("tech") == "Technology"
    assert normalize_sector("Technology") == "Technology"
    assert normalize_sector("it") == "Technology"
    assert normalize_sector("healthcare") == "Healthcare"
    assert normalize_sector("financials") == "Financial Services"
    assert normalize_sector("energy") == "Energy"
    assert normalize_sector(None) is None
    assert normalize_sector("") is None


def test_format_quotes_extracts_clean_fields():
    """_format_quotes extracts financial attributes into normalized candidate dictionaries."""
    mock_quotes = [
        {
            "symbol": "NVDA",
            "shortName": "NVIDIA Corporation",
            "regularMarketPrice": 120.5,
            "marketCap": 3000000000000.0,
            "trailingPE": 45.2,
            "forwardPE": 28.1,
            "averageAnalystRating": "1.4 - Strong Buy",
            "fullExchangeName": "NasdaqGS",
        },
        {
            "symbol": "MSFT",
            "longName": "Microsoft Corporation",
            "fulldayPrice": 440.0,
            "marketCap": 3200000000000.0,
            "trailingPE": 35.0,
            "forwardPE": 29.5,
            "averageAnalystRating": "1.6 - Buy",
            "exchange": "NMS",
        },
    ]
    records = _format_quotes(mock_quotes, limit=2)
    assert len(records) == 2
    assert records[0]["ticker"] == "NVDA"
    assert records[0]["company"] == "NVIDIA Corporation"
    assert records[0]["price"] == 120.5
    assert records[0]["market_cap"] == 3000000000000.0
    assert records[0]["trailing_pe"] == 45.2
    assert "Market Cap: $3000.0B" in records[0]["summary"]

    assert records[1]["ticker"] == "MSFT"
    assert records[1]["company"] == "Microsoft Corporation"
    assert records[1]["price"] == 440.0


def test_execute_equity_screen_preset_with_mock():
    """Preset execution passes screener ID and returns formatted candidates."""
    mock_quotes = [
        {
            "symbol": "AMD",
            "shortName": "Advanced Micro Devices",
            "regularMarketPrice": 150.0,
            "marketCap": 240000000000.0,
            "trailingPE": 110.0,
        }
    ]
    with patch("app.market.screener._screen_yfinance", return_value={"quotes": mock_quotes}) as mock_yf:
        res = execute_equity_screen(preset="growth_technology_stocks", limit=5)
        assert res["status"] == "ok"
        assert res["count"] == 1
        assert res["preset"] == "growth_technology_stocks"
        assert res["records"][0]["ticker"] == "AMD"
        mock_yf.assert_called_once_with("growth_technology_stocks", count=5)


def test_execute_equity_screen_custom_criteria():
    """Custom criteria constructs query with sector and market cap filters."""
    mock_quotes = [
        {
            "symbol": "GOOGL",
            "shortName": "Alphabet Inc.",
            "regularMarketPrice": 175.0,
            "marketCap": 2200000000000.0,
            "trailingPE": 26.0,
        }
    ]
    with patch("app.market.screener._screen_yfinance", return_value={"quotes": mock_quotes}) as mock_yf:
        res = execute_equity_screen(
            sector="tech",
            min_market_cap=100000000000.0,
            max_pe_ratio=30.0,
            limit=3,
        )
        assert res["status"] == "ok"
        assert res["count"] == 1
        assert res["sector"] == "Technology"
        assert res["records"][0]["ticker"] == "GOOGL"
        assert mock_yf.call_count == 1


def test_execute_equity_screen_handles_exception():
    """Exceptions are caught and returned as status='error' with empty records list."""
    with patch("app.market.screener._screen_yfinance", side_effect=RuntimeError("Yahoo Finance timeout")):
        res = execute_equity_screen(preset="growth_technology_stocks")
        assert res["status"] == "error"
        assert "Yahoo Finance timeout" in res["message"]
        assert res["records"] == []


def test_screen_stocks_tool_invocation():
    """screen_stocks tool in create_agent_tools executes and wraps output in JSON."""
    tools = create_agent_tools()
    screen_tool = next((t for t in tools if t.name == "screen_stocks"), None)
    assert screen_tool is not None, "screen_stocks tool must be registered in create_agent_tools"

    mock_quotes = [
        {
            "symbol": "AVGO",
            "shortName": "Broadcom Inc.",
            "regularMarketPrice": 160.0,
            "marketCap": 750000000000.0,
        }
    ]
    with patch("app.market.screener._screen_yfinance", return_value={"quotes": mock_quotes}):
        raw_res = screen_tool.invoke({
            "sector": "Technology",
            "min_market_cap": 50000000000.0,
            "candidate_id": "cand_avgo",
            "limit": 2,
        })
        parsed = json.loads(raw_res)
        assert parsed["status"] == "ok"
        assert parsed["candidate_id"] == "cand_avgo"
        assert parsed["count"] == 1
        assert parsed["records"][0]["ticker"] == "AVGO"
