"""Tests for app.agent.tools registry and duplicate call protection."""
from unittest.mock import patch, MagicMock
import pytest
from app.agent.tools import create_agent_tools, ToolCallGuard


def test_tool_registry_contains_all_10_tools():
    tools = create_agent_tools()
    tool_names = {t.name for t in tools}
    expected = {
        "search_social",
        "search_articles",
        "read_article",
        "search_web",
        "get_market_data",
        "get_company_research",
        "list_sec_filings",
        "pull_sec_filings",
        "verify_sec_claim",
        "get_sec_financials",
    }
    assert tool_names == expected


def test_duplicate_call_guard_suppresses_repeated_calls():
    guard = ToolCallGuard(max_identical=2)
    sig = ("search_web", (("query", "NVDA partnership"),))

    # First two calls allowed
    assert guard.check_and_record(sig) is False
    assert guard.check_and_record(sig) is False

    # Third identical call suppressed
    assert guard.check_and_record(sig) is True


def test_tool_execution_catches_errors_gracefully():
    tools = create_agent_tools()
    market_tool = next(t for t in tools if t.name == "get_market_data")

    # Invalid ticker should return structured error string, not crash loop
    res = market_tool.invoke({"ticker": ""})
    assert "error" in str(res).lower() or "invalid" in str(res).lower()
