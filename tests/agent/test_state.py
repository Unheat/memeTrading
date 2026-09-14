"""Tests for app.agent.state, prompts, and context management."""
import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.agent.context import (
    ModelContextPolicy,
    conservative_token_counter,
    prepare_context,
    trim_conversation_history,
)
from app.agent.state import ResearchRequest, BudgetLimits, create_initial_state
from app.agent.prompts import build_dynamic_system_prompt, FORENSIC_CHARTER_PROMPT


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
    """Verify every dynamic fact is projected with exact JSON serialization."""
    req = ResearchRequest(query="Analyze ABC", ticker="ABC")
    state = create_initial_state(req, case_id="case_abc")
    expected_projections = {
        "Current Unresolved Questions": ["Is contract binding?", "What is warrant overhang?"],
        "Verified Evidence Accumulated": [{"source": "8-K", "quote": "non-binding"}],
        "Contradictions Observed": [{"claim": "binding", "reason": "LOI language"}],
        "Market Context": {"price": 12.5, "currency": "USD"},
        "Consensus Snapshot": {"revenue": None, "analysts": 3},
        "SEC Corpora": ["8-K: accession 123"],
        "Confidence": 0.625,
        "Causal Chain": {"promotion": "volume", "volume": "price"},
        "Searches Performed": [{"tool": "search_articles", "query": "ABC contract", "hits": 2}],
    }
    state.update({
        "unresolved_questions": expected_projections["Current Unresolved Questions"],
        "evidence": expected_projections["Verified Evidence Accumulated"],
        "contradictions": expected_projections["Contradictions Observed"],
        "market_context": expected_projections["Market Context"],
        "consensus_snapshot": expected_projections["Consensus Snapshot"],
        "sec_corpora": expected_projections["SEC Corpora"],
        "confidence": expected_projections["Confidence"],
        "causal_chain": expected_projections["Causal Chain"],
        "searches_performed": expected_projections["Searches Performed"],
        "tool_calls": 3,
    })

    content = build_dynamic_system_prompt(state).content

    assert "ABC" in content
    assert "Remaining tool calls**: 12" in content
    for label, value in expected_projections.items():
        assert f"- **{label}**:\n```json\n{json.dumps(value, indent=2)}\n```" in content


def test_trim_conversation_history():
    """Verify the compatibility wrapper keeps recent history."""
    messages = [
        HumanMessage(content="Start investigation"),
        AIMessage(content="Calling search_social"),
        HumanMessage(content="Social result: high velocity"),
        AIMessage(content="Calling verify_sec_claim"),
        HumanMessage(content="SEC verification: CONTRADICTED"),
    ]
    trimmed = trim_conversation_history(messages, max_tokens=100)
    assert 0 < len(trimmed) <= len(messages)
    assert trimmed[-1].content == "SEC verification: CONTRADICTED"


def test_model_context_policy_defaults_to_million_token_capacity() -> None:
    """Verify default policy uses modern capacity and a high compaction threshold."""
    policy = ModelContextPolicy()
    assert policy.context_window_tokens == 1_000_000
    assert policy.compact_threshold_tokens == 200_000
    assert policy.max_input_tokens == 936_000


def test_model_context_policy_rejects_exhausted_input_capacity() -> None:
    """Verify output reserve and safety margin cannot consume the whole window."""
    with pytest.raises(ValueError, match="positive input capacity"):
        ModelContextPolicy(
            context_window_tokens=100,
            reserved_output_tokens=50,
            safety_margin_tokens=50,
            compact_threshold_tokens=1,
        )


def test_prepare_context_preserves_history_below_threshold():
    """Verify preparation returns identical message objects below threshold."""
    messages = [HumanMessage(content="question"), AIMessage(content="answer")]
    prepared = prepare_context(messages, token_counter=lambda _: 2)
    assert prepared.messages == tuple(messages)
    assert prepared.messages[0] is messages[0]
    assert prepared.compacted is False
    assert prepared.original_tokens == prepared.prepared_tokens == 2


def test_counter_includes_tool_call_arguments_and_ids():
    """Verify conservative counting includes hidden AI call data and pair IDs."""
    plain = [AIMessage(content="")]
    paired = [
        AIMessage(content="", tool_calls=[{"name": "lookup", "args": {"query": "x" * 80}, "id": "call-123"}]),
        ToolMessage(content="ok", tool_call_id="call-123", name="lookup"),
    ]
    assert conservative_token_counter(paired) > conservative_token_counter(plain)


def test_prepare_context_prunes_old_tool_body_and_retains_pair_metadata():
    """Verify old oversized tool output is replaced without breaking its call pair."""
    messages = [
        HumanMessage(content="old question"),
        AIMessage(content="", tool_calls=[{"name": "lookup", "args": {"q": "old"}, "id": "old-call"}]),
        ToolMessage(content="z" * 400, tool_call_id="old-call", name="lookup", status="success"),
        AIMessage(content="old answer"),
        HumanMessage(content="latest question"),
        AIMessage(content="latest answer"),
    ]
    policy = ModelContextPolicy(
        context_window_tokens=180,
        reserved_output_tokens=0,
        safety_margin_tokens=0,
        compact_threshold_tokens=1,
        tool_result_max_tokens=20,
        latest_units_to_preserve=1,
    )
    prepared = prepare_context(messages, policy=policy)
    tool_message = next(message for message in prepared.messages if isinstance(message, ToolMessage))
    metadata = json.loads(tool_message.content)
    assert metadata == {
        "digest": "6768a45ee86cc3da",
        "id": "old-call",
        "name": "lookup",
        "size": 400,
        "status": "success",
    }
    assert tool_message.tool_call_id == "old-call"
    assert prepared.messages[-2:] == tuple(messages[-2:])


def test_prepare_context_drops_oldest_complete_unit_and_keeps_latest():
    """Verify hard-limit trimming drops whole old units and preserves newest unit."""
    old_unit = [
        HumanMessage(content="old"),
        AIMessage(content="", tool_calls=[{"name": "lookup", "args": {}, "id": "old-call"}]),
        ToolMessage(content="old result", tool_call_id="old-call", name="lookup"),
        AIMessage(content="old answer"),
    ]
    latest_unit = [HumanMessage(content="latest"), AIMessage(content="latest answer")]

    def count_messages(messages):
        """Return deterministic per-message cost for unit-dropping test input."""
        return len(messages) * 10

    policy = ModelContextPolicy(
        context_window_tokens=20,
        reserved_output_tokens=0,
        safety_margin_tokens=0,
        compact_threshold_tokens=1,
        tool_result_max_tokens=100,
        latest_units_to_preserve=1,
    )
    prepared = prepare_context([*old_unit, *latest_unit], policy=policy, token_counter=count_messages)
    assert prepared.messages == tuple(latest_unit)
    assert prepared.prepared_tokens == 20


@pytest.mark.parametrize(
    "messages",
    [
        [ToolMessage(content="orphan", tool_call_id="missing")],
        [AIMessage(content="", tool_calls=[{"name": "lookup", "args": {}, "id": "unmatched"}])],
        [
            AIMessage(content="", tool_calls=[{"name": "lookup", "args": {}, "id": "call-1"}]),
            HumanMessage(content="interrupt"),
            ToolMessage(content="late", tool_call_id="call-1"),
        ],
    ],
)
def test_prepare_context_rejects_invalid_tool_pairs(messages):
    """Verify orphaned, unmatched, and interrupted AI/tool pairs fail fast."""
    with pytest.raises(ValueError):
        prepare_context(messages)
