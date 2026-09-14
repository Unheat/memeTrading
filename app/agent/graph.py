"""LangGraph workflow for outer market research agent.

Donor provenance: adapted from reference/ai-financial-research-agent/app/agent/graph.py:25-208
(StateGraph loop, should_continue conditional edge, ToolNode) with dynamic system prompt,
ephemeral context trimming, and budget stopping limits.
"""
from __future__ import annotations

import logging
from typing import Any, Literal, Sequence
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from app.agent.adversarial import run_adversarial_red_team
from app.agent.committee import run_investment_committee
from app.agent.context import ModelContextPolicy, TokenCounter, conservative_token_counter, prepare_context
from app.agent.prompts import build_dynamic_system_prompt
from app.agent.state import InvestigationState
from app.agent.tool_result_ingestion import ingest_tool_results

logger = logging.getLogger(__name__)


def should_continue(state: InvestigationState) -> Literal["tools", "red_team"]:
    """Determine whether to execute tool calls or route to adversarial red team."""
    messages = state.get("messages", [])
    if not messages:
        return "red_team"

    last_message = messages[-1]
    tool_calls = getattr(last_message, "tool_calls", None)
    if not tool_calls:
        return "red_team"

    budget = state.get("budget_state", {})
    max_tool_calls = budget.get("max_tool_calls", 15)
    current_calls = state.get("tool_calls", 0)

    previous_calls = current_calls - len(tool_calls)
    remaining_allowed_calls = max_tool_calls - previous_calls
    if remaining_allowed_calls <= 0:
        logger.info("Budget limit reached (%d >= %d); proceeding to red team audit.", current_calls, max_tool_calls)
        return "red_team"

    return "tools"


def create_agent_graph(
    model: Any,
    tools: Sequence[BaseTool],
    checkpointer: Any | None = None,
    context_policy: ModelContextPolicy | None = None,
    token_counter: TokenCounter = conservative_token_counter,
):
    """Compile the 3-Stage Institutional Research Agent workflow.

    Stage 1: Forensic Investigator (free-loop tool calling)
    Stage 2: Air-Gapped Adversarial Red Team (short-seller attack & kill criteria)
    Stage 3: Investment Committee (CIO 3:1 asymmetry, passing discipline, Kelly sizing)
    """
    model_with_tools = model.bind_tools(tools) if hasattr(model, "bind_tools") else model
    active_context_policy = context_policy or ModelContextPolicy()

    def agent_node(state: InvestigationState) -> dict[str, Any]:
        """Invoke investigator with adaptive, pair-safe model context."""
        sys_msg = build_dynamic_system_prompt(state)
        prepared = prepare_context(
            [sys_msg, *state.get("messages", [])],
            policy=active_context_policy,
            token_counter=token_counter,
        )

        response = model_with_tools.invoke(list(prepared.messages))

        current_calls = state.get("tool_calls", 0)
        max_tool_calls = state.get("budget_state", {}).get("max_tool_calls", 15)
        remaining_calls = max(0, max_tool_calls - current_calls)
        allowed_tool_calls = list(getattr(response, "tool_calls", None) or [])[
            :remaining_calls
        ]
        if isinstance(response, AIMessage) and allowed_tool_calls != response.tool_calls:
            response = response.model_copy(update={"tool_calls": allowed_tool_calls})

        return {
            "messages": [response],
            "tool_calls": current_calls + len(allowed_tool_calls),
        }

    def ingest_tool_results_node(state: InvestigationState) -> dict[str, Any]:
        """Ingest the trailing contiguous ToolMessages from accumulated graph state."""
        messages = state.get("messages", [])
        first_tool_index = len(messages)
        while first_tool_index and isinstance(messages[first_tool_index - 1], ToolMessage):
            first_tool_index -= 1
        return ingest_tool_results(state, messages[first_tool_index:])

    def red_team_node(state: InvestigationState) -> dict[str, Any]:
        """Stage 2: Air-gapped adversarial short-seller attack."""
        return run_adversarial_red_team(state, model=model)

    def committee_node(state: InvestigationState) -> dict[str, Any]:
        """Stage 3: Investment Committee deliberation and position sizing."""
        return run_investment_committee(state, model=model)

    tool_node = ToolNode(tools)

    workflow = StateGraph(InvestigationState)
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tool_node)
    workflow.add_node("ingest_tool_results", ingest_tool_results_node)
    workflow.add_node("adversarial_red_team", red_team_node)
    workflow.add_node("investment_committee", committee_node)

    workflow.set_entry_point("agent")
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            "red_team": "adversarial_red_team",
        },
    )
    workflow.add_edge("tools", "ingest_tool_results")
    workflow.add_edge("ingest_tool_results", "agent")
    workflow.add_edge("adversarial_red_team", "investment_committee")
    workflow.add_edge("investment_committee", END)

    return workflow.compile(checkpointer=checkpointer)
