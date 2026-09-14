"""Tests for LangGraph state graph execution using ScriptedModel."""
from unittest.mock import MagicMock
import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from app.agent.state import ResearchRequest, create_initial_state
from app.agent.graph import create_agent_graph


class ScriptedModel:
    """Deterministic offline model for graph workflow testing."""

    def __init__(self):
        self.call_count = 0

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        self.call_count += 1
        if self.call_count == 1:
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "fake_search",
                        "args": {"query": "XYZ partnership"},
                        "id": "call_1",
                        "type": "tool_call",
                    }
                ],
            )
        elif self.call_count == 2:
            return AIMessage(
                content="Forensic synthesis: XYZ partnership claim is contradicted by 8-K."
            )
        elif self.call_count == 3:
            return AIMessage(
                content="""{
  "falsifiable_objections": ["Objection 1", "Objection 2"],
  "numeric_kill_criteria": ["Kill Trigger 1: Gross margin drop", "Kill Trigger 2: DSI increase"],
  "bear_floor_price": 75.0,
  "bear_thesis_summary": "Cyclical trap."
}"""
            )
        return AIMessage(content="CIO deliberation: HIGH CONVICTION.")


@tool
def fake_search(query: str) -> str:
    """Fake search tool."""
    return '{"status": "ok", "result": "found 8-K showing non-binding LOI"}'


def test_agent_graph_execution_loop():
    model = ScriptedModel()
    graph = create_agent_graph(model=model, tools=[fake_search])

    req = ResearchRequest(query="Investigate XYZ", ticker="XYZ")
    initial_state = create_initial_state(req, case_id="case_test")

    final_state = graph.invoke(initial_state)

    assert final_state["tool_calls"] == 1
    assert len(final_state["messages"]) >= 3
    # Check 3-Stage pipeline artifacts
    assert "thesis_breakers" in final_state
    assert len(final_state["thesis_breakers"]) >= 2
    assert "Kill Trigger 1" in final_state["thesis_breakers"][0]
    assert "ic_verdict" in final_state
    assert final_state["ic_verdict"].ticker == "XYZ"


def test_agent_graph_stops_at_budget_limit():
    class InfiniteLoopModel:
        def __init__(self):
            self.call_count = 0

        def bind_tools(self, tools):
            return self

        def invoke(self, messages):
            self.call_count += 1
            if self.call_count <= 2:
                return AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "fake_search",
                            "args": {"query": "loop query"},
                            "id": f"call_{self.call_count}",
                            "type": "tool_call",
                        }
                    ],
                )
            elif self.call_count == 3:
                return AIMessage(
                    content="""{
  "falsifiable_objections": ["Objection 1"],
  "numeric_kill_criteria": ["Kill Trigger 1: Margin drop"],
  "bear_floor_price": 50.0,
  "bear_thesis_summary": "Trap."
}"""
                )
            return AIMessage(content="CIO deliberation: PASSED.")

    model = InfiniteLoopModel()
    graph = create_agent_graph(model=model, tools=[fake_search])

    req = ResearchRequest(query="Investigate loop", ticker="XYZ")
    initial_state = create_initial_state(req, case_id="case_loop")
    initial_state["budget_state"]["max_tool_calls"] = 2  # low budget limit

    final_state = graph.invoke(initial_state)
    assert final_state["tool_calls"] >= 2
    assert "ic_verdict" in final_state
