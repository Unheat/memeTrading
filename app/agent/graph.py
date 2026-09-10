"""LangGraph workflow for outer market research agent.

Donor provenance: adapted from reference/ai-financial-research-agent/app/agent/graph.py:25-208
(StateGraph loop, should_continue conditional edge, ToolNode) with dynamic system prompt,
ephemeral context trimming, and budget stopping limits.
"""
from __future__ import annotations

import logging
from typing import Any, Literal, Sequence
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from app.agent.context import trim_conversation_history
from app.agent.prompts import build_dynamic_system_prompt
from app.agent.state import InvestigationState

logger = logging.getLogger(__name__)


def should_continue(state: InvestigationState) -> Literal["tools", "end"]:
    """Determine whether to execute tool calls or terminate."""
    messages = state.get("messages", [])
    if not messages:
        return "end"

    last_message = messages[-1]
    tool_calls = getattr(last_message, "tool_calls", None)
    if not tool_calls:
        return "end"

    budget = state.get("budget_state", {})
    max_tool_calls = budget.get("max_tool_calls", 15)
    current_calls = state.get("tool_calls", 0)

    if current_calls >= max_tool_calls:
        logger.info("Budget limit reached (%d >= %d); terminating research loop.", current_calls, max_tool_calls)
        return "end"

    return "tools"


def create_agent_graph(
    model: Any,
    tools: Sequence[BaseTool],
    checkpointer: Any | None = None,
):
    """Compile the LangGraph research agent workflow.

    :param model: Chat model supporting .bind_tools() or scripted test model.
    :param tools: Sequence of 8 normalized BaseTool instances.
    :param checkpointer: Optional LangGraph checkpoint saver.
    :returns: Compiled LangGraph Pregel application.
    """
    model_with_tools = model.bind_tools(tools) if hasattr(model, "bind_tools") else model

    def agent_node(state: InvestigationState) -> dict[str, Any]:
        """Invoke agent with dynamic structured system prompt and trimmed history."""
        sys_msg = build_dynamic_system_prompt(state)
        history = trim_conversation_history(state.get("messages", []))

        response = model_with_tools.invoke([sys_msg, *history])

        new_tool_calls = len(getattr(response, "tool_calls", None) or [])
        updated_tool_calls = state.get("tool_calls", 0) + new_tool_calls

        return {
            "messages": [response],
            "tool_calls": updated_tool_calls,
        }

    tool_node = ToolNode(tools)

    workflow = StateGraph(InvestigationState)
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tool_node)

    workflow.set_entry_point("agent")
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            "end": END,
        },
    )
    workflow.add_edge("tools", "agent")

    return workflow.compile(checkpointer=checkpointer)
