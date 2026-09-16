"""Tests for deep-research evidence-gap reflection and multi-round investigation."""
from __future__ import annotations

import json
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool

from app.agent.graph import create_research_graph, _has_evidence_gaps
from app.agent.state import ResearchRequest, create_initial_state


@tool
def fake_discovery(query: str) -> str:
    """Return a discovery result with a linked PDF."""
    return json.dumps({
        "status": "ok",
        "results": [{"title": "Cloud PDF", "url": "https://example.test/cloud-report.pdf"}],
    })


@tool
def fake_read_doc(url: str, candidate_id: str | None = None) -> str:
    """Return an extracted document result."""
    return json.dumps({
        "status": "ok",
        "url": url,
        "text": "Deep cloud revenue metrics extracted.",
        "candidate_id": candidate_id,
    })


class ReflectiveModel:
    """Model that proposes discovery first, then responds to reflection by reading documents."""

    def __init__(self) -> None:
        self.turns = 0

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        self.turns += 1
        last_msg = messages[-1]
        # Turn 1: Discover documents
        if self.turns == 1:
            return AIMessage(
                content="",
                tool_calls=[{"name": "fake_discovery", "args": {"query": "AI Capex"}, "id": "call-disc", "type": "tool_call"}],
            )
        # Turn 2: Initial premature text response with unread PDF links in state
        if self.turns == 2:
            return AIMessage(content="Preliminary scan finished.")
        # Turn 3: Received deep reflection prompt -> issues read_doc tool call!
        if self.turns == 3:
            assert "DEEP RESEARCH GAP REFLECTION" in str(getattr(last_msg, "content", ""))
            return AIMessage(
                content="",
                tool_calls=[{"name": "fake_read_doc", "args": {"url": "https://example.test/cloud-report.pdf"}, "id": "call-read", "type": "tool_call"}],
            )
        # Turn 4: Final synthesis after deep reading
        return AIMessage(content="Final deep research synthesis: primary cloud report verified.")


def test_has_evidence_gaps_detects_unread_discovered_documents() -> None:
    """Verify _has_evidence_gaps identifies unread PDF documents."""
    state = create_initial_state(ResearchRequest(query="Research cloud"), "test-gap-1")
    assert _has_evidence_gaps(state) is False

    state["source_records"].append({
        "tool": "search_web",
        "url": "https://example.com/deck.pdf",
        "status": "discovered",
    })
    assert _has_evidence_gaps(state) is True

    state["source_records"][0]["status"] = "read"
    assert _has_evidence_gaps(state) is False


def test_has_evidence_gaps_detects_incomplete_candidate_data() -> None:
    """Verify _has_evidence_gaps identifies candidate companies missing SEC/market context."""
    state = create_initial_state(ResearchRequest(query="Rank 2 AI stocks"), "test-gap-2")
    state["candidates"]["cand_1"] = {
        "candidate_id": "cand_1",
        "ticker": "NVDA",
        "market_context": None,
    }
    assert _has_evidence_gaps(state) is True

    state["candidates"]["cand_1"]["market_context"] = {"quote": {"price": 120}}
    state["candidates"]["cand_1"]["sec_financials"] = {"periods": ["2026-Q1"]}
    state["comparisons"] = [{"comparison_id": "comp_1"}]
    assert _has_evidence_gaps(state) is False


def test_reflection_node_prompts_model_to_deepen_evidence() -> None:
    """Verify reflection loop prompts model when gaps exist and model continues digging."""
    model = ReflectiveModel()
    graph = create_research_graph(model=model, tools=[fake_discovery, fake_read_doc])

    initial = create_initial_state(ResearchRequest(query="Research AI Capex"), "reflection-case")
    initial["source_records"].append({
        "tool": "search_web",
        "url": "https://example.test/cloud-report.pdf",
        "status": "discovered",
    })

    final = graph.invoke(initial)
    assert model.turns >= 3
    assert final["status"] == "completed"
    # Verify read_doc was called in response to reflection
    receipts = [r["tool"] for r in final["searches_performed"]]
    assert "fake_read_doc" in receipts
