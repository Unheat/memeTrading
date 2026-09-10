"""Tests for app.agent.state, prompts, and context management."""
import pytest
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from app.agent.state import ResearchRequest, BudgetLimits, create_initial_state
from app.agent.prompts import build_dynamic_system_prompt, FORENSIC_CHARTER_PROMPT
from app.agent.context import trim_conversation_history


def test_budget_limits_defaults():
    budget = BudgetLimits()
    assert budget.max_tool_calls == 15
    assert budget.max_identical_calls == 2


def test_research_request_validation():
    req = ResearchRequest(query="Investigate NVDA hype", ticker="nvda")
    assert req.ticker == "NVDA"
    assert req.query == "Investigate NVDA hype"
    assert req.budget.max_tool_calls == 15

    with pytest.raises(ValueError, match="query"):
        ResearchRequest(query="")


def test_create_initial_state():
    req = ResearchRequest(query="Is XYZ partnership real?", ticker="XYZ", company="XYZ Corp")
    state = create_initial_state(req, case_id="case_123")
    assert state["case_id"] == "case_123"
    assert state["ticker"] == "XYZ"
    assert state["company"] == "XYZ Corp"
    assert state["tool_calls"] == 0
    assert state["status"] == "in_progress"
    assert len(state["messages"]) == 1
    assert isinstance(state["messages"][0], HumanMessage)
    assert "Is XYZ partnership real?" in state["messages"][0].content


def test_build_dynamic_system_prompt():
    req = ResearchRequest(query="Analyze ABC", ticker="ABC")
    state = create_initial_state(req, case_id="case_abc")
    state["unresolved_questions"] = ["Is contract binding?", "What is warrant overhang?"]
    state["evidence"] = [
        {"source": "8-K", "quote": "Agreement is non-binding LOI", "verdict": "CONTRADICTED"}
    ]
    state["tool_calls"] = 3

    sys_msg = build_dynamic_system_prompt(state)
    assert isinstance(sys_msg, SystemMessage)
    content = sys_msg.content
    assert "ABC" in content
    assert "Agreement is non-binding LOI" in content
    assert "Is contract binding?" in content
    assert "Remaining tool calls**: 12" in content  # 15 - 3


def test_trim_conversation_history():
    messages = [
        HumanMessage(content="Start investigation"),
        AIMessage(content="Calling search_social"),
        HumanMessage(content="Social result: high velocity"),
        AIMessage(content="Calling verify_sec_claim"),
        HumanMessage(content="SEC verification: CONTRADICTED"),
    ]
    # Trim with a small token cap (e.g. 50 tokens)
    trimmed = trim_conversation_history(messages, max_tokens=100)
    assert len(trimmed) <= len(messages)
    assert len(trimmed) > 0
    # Must keep recent messages
    assert trimmed[-1].content == "SEC verification: CONTRADICTED"
