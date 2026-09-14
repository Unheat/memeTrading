"""Tests for LangGraph state graph execution using ScriptedModel."""
import json

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool

from app.agent import graph as graph_module
from app.agent.graph import create_agent_graph
from app.agent.state import ResearchRequest, create_initial_state


class ScriptedModel:
    """Deterministic offline model for graph workflow testing."""

    def __init__(self):
        """Initialize model invocation count."""
        self.call_count = 0

    def bind_tools(self, tools):
        """Return this deterministic model after accepting graph tools."""
        return self

    def invoke(self, messages):
        """Return the next scripted response for the three-stage workflow."""
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
        if self.call_count == 2:
            return AIMessage(
                content="Forensic synthesis: XYZ partnership claim is contradicted by 8-K."
            )
        if self.call_count == 3:
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
    """Return a deterministic fake search result."""
    return '{"status": "ok", "result": "found 8-K showing non-binding LOI"}'


@tool
def get_market_data(ticker: str) -> str:
    """Return deterministic market context for graph ingestion tests."""
    return json.dumps({"status": "ok", "ticker": ticker, "price": 101.5})


@tool
def get_company_research(ticker: str) -> str:
    """Return deterministic consensus context for graph ingestion tests."""
    return json.dumps({"status": "ok", "ticker": ticker, "ratings": {"buy": 4}})


def test_agent_graph_execution_loop():
    model = ScriptedModel()
    graph = create_agent_graph(model=model, tools=[fake_search])

    req = ResearchRequest(query="Investigate XYZ", ticker="XYZ")
    initial_state = create_initial_state(req, case_id="case_test")

    final_state = graph.invoke(initial_state)

    assert final_state["tool_calls"] == 1
    assert len(final_state["messages"]) >= 3
    assert "thesis_breakers" in final_state
    assert len(final_state["thesis_breakers"]) >= 2
    assert "Kill Trigger 1" in final_state["thesis_breakers"][0]
    assert "ic_verdict" in final_state
    assert final_state["ic_verdict"].ticker == "XYZ"


def test_market_and_parallel_tool_results_are_ingested_before_committee(monkeypatch):
    """Prove parallel tool results merge and market context reaches committee state."""
    observed_committee_state = {}

    class ParallelToolModel:
        """Request two tools in parallel, then finish investigation."""

        def __init__(self):
            """Initialize model invocation count."""
            self.call_count = 0

        def bind_tools(self, tools):
            """Return this deterministic model after accepting graph tools."""
            return self

        def invoke(self, messages):
            """Request parallel context tools once, then return synthesis text."""
            self.call_count += 1
            if self.call_count == 1:
                return AIMessage(
                    content="",
                    tool_calls=[
                        {"name": "get_market_data", "args": {"ticker": "XYZ"}, "id": "market-1", "type": "tool_call"},
                        {"name": "get_company_research", "args": {"ticker": "XYZ"}, "id": "research-1", "type": "tool_call"},
                    ],
                )
            return AIMessage(content="Investigation complete.")

    def fake_red_team(state, model):
        """Return minimal red-team output without invoking model."""
        return {"thesis_breakers": ["Kill Trigger 1"]}

    def fake_committee(state, model):
        """Capture committee input state and return a marker verdict."""
        observed_committee_state.update(state)
        return {"ic_verdict": "passed"}

    monkeypatch.setattr(graph_module, "run_adversarial_red_team", fake_red_team)
    monkeypatch.setattr(graph_module, "run_investment_committee", fake_committee)
    graph = create_agent_graph(
        model=ParallelToolModel(), tools=[get_market_data, get_company_research]
    )
    initial_state = create_initial_state(
        ResearchRequest(query="Investigate XYZ", ticker="XYZ"), case_id="parallel"
    )

    final_state = graph.invoke(initial_state)

    assert observed_committee_state["market_context"]["price"] == 101.5
    assert observed_committee_state["consensus_snapshot"]["ratings"] == {"buy": 4}
    assert [receipt["tool_call_id"] for receipt in final_state["searches_performed"]] == [
        "market-1",
        "research-1",
    ]


def test_agent_graph_executes_exact_remaining_tool_budget(monkeypatch):
    """Prove excess parallel calls are clipped while allowed call pairs stay complete."""
    executed_queries = []

    @tool
    def budgeted_search(query: str) -> str:
        """Record each allowed execution and return a JSON result."""
        executed_queries.append(query)
        return json.dumps({"status": "ok", "query": query})

    class ExcessToolModel:
        """Return more parallel calls than remaining budget allows."""

        def __init__(self):
            """Initialize model invocation count."""
            self.call_count = 0

        def bind_tools(self, tools):
            """Return this deterministic model after accepting graph tools."""
            return self

        def invoke(self, messages):
            """Offer three tool calls on first invocation, then finish."""
            self.call_count += 1
            if self.call_count == 1:
                return AIMessage(
                    content="",
                    tool_calls=[
                        {"name": "budgeted_search", "args": {"query": query}, "id": f"call-{index}", "type": "tool_call"}
                        for index, query in enumerate(("one", "two", "three"), start=1)
                    ],
                )
            return AIMessage(content="Investigation complete.")

    monkeypatch.setattr(
        graph_module,
        "run_adversarial_red_team",
        lambda state, model: {"thesis_breakers": ["budget reached"]},
    )
    monkeypatch.setattr(
        graph_module,
        "run_investment_committee",
        lambda state, model: {"ic_verdict": "passed"},
    )
    graph = create_agent_graph(model=ExcessToolModel(), tools=[budgeted_search])
    initial_state = create_initial_state(
        ResearchRequest(query="Investigate budget", ticker="XYZ"), case_id="budget"
    )
    initial_state["budget_state"]["max_tool_calls"] = 2

    final_state = graph.invoke(initial_state)

    assert final_state["tool_calls"] == 2
    assert executed_queries == ["one", "two"]
    ai_tool_calls = [
        call
        for message in final_state["messages"]
        if isinstance(message, AIMessage)
        for call in message.tool_calls
    ]
    tool_messages = [
        message for message in final_state["messages"] if isinstance(message, ToolMessage)
    ]
    assert [call["id"] for call in ai_tool_calls] == ["call-1", "call-2"]
    assert [message.tool_call_id for message in tool_messages] == ["call-1", "call-2"]
