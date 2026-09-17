"""Tests for prompt-directed research intent and the single research graph."""
from __future__ import annotations

from langchain_core.messages import AIMessage
from langchain_core.tools import tool

from app.agent.graph import create_research_graph
from app.agent.memo import render_research_report
from app.agent.state import ResearchRequest, create_initial_state


class ScriptedModel:
    """Return one source lookup and a final evidence-calibrated synthesis."""

    def __init__(self) -> None:
        """Initialize the invocation counter."""
        self.calls = 0

    def bind_tools(self, tools):
        """Accept the model-visible tool list."""
        return self

    def invoke(self, messages):
        """Request a source once, then complete the research loop."""
        self.calls += 1
        if self.calls == 1:
            return AIMessage(content="", tool_calls=[{"name": "search_web", "args": {"query": "used car pricing"}, "id": "web-1", "type": "tool_call"}])
        return AIMessage(content="The source supports comparing local prices.")


@tool
def search_web(query: str) -> str:
    """Return one generic discovery record."""
    return '{"status":"ok","results":[{"title":"Vehicle listing","url":"https://example.test/listing"}]}'


def test_intent_preserves_prompt_requested_ranking_count() -> None:
    """Keep user-selected output counts instead of defaulting to a shortlist size."""
    assert ResearchRequest(query="Rank the best 10 tech stocks", requested_ranking_count=10).resolve_intent().requested_ranking_count == 10
    assert ResearchRequest(query="Compare 3 AI companies", requested_ranking_count=3).resolve_intent().requested_ranking_count == 3
    assert ResearchRequest(query="Research a used car").resolve_intent().requested_ranking_count is None

    # Verify structured plan intent preserves requested ranking count without regexes
    from app.agent.state import ResearchIntent
    plan = {"brief": "Rank 5 stocks", "research_type": "multi_candidate_ranking", "ranking_count": 5}
    assert ResearchIntent.from_plan(plan).requested_ranking_count == 5


def test_initial_state_has_no_profile_or_mode() -> None:
    """Expose only model guidance and evidence containers in initial state."""
    state = create_initial_state(ResearchRequest(query="Rank the best 7 companies", requested_ranking_count=7), "intent-1")
    assert "profile" not in state
    assert "mode" not in state
    assert state["research_intent"]["requested_ranking_count"] == 7
    assert state["research_intent"]["requires_candidate_workspaces"] is True


def test_one_graph_runs_general_research_to_source_backed_completion() -> None:
    """Use the central graph for a non-investment research request."""
    final_state = create_research_graph(ScriptedModel(), [search_web]).invoke(
        create_initial_state(ResearchRequest(query="Find a used car"), "intent-2")
    )
    assert final_state["status"] == "completed"
    assert final_state["source_records"][0]["url"] == "https://example.test/listing"
    assert final_state["market_context"] is None


def test_report_discloses_requested_count_and_evidence_gap() -> None:
    """Never represent an incomplete ranking as a complete shortlist."""
    state = create_initial_state(ResearchRequest(query="Rank the best 5 companies", requested_ranking_count=5), "intent-3")
    state["status"] = "research_incomplete"
    state["evidence_gate"] = {"missing_evidence": ["Requested 5 evidence-backed candidates; collected 0."]}
    report = render_research_report(state, "Evidence collection is incomplete.")
    assert "Requested ranking count: 5" in report
    assert "collected 0" in report
    assert "SCREEN_SHORTLIST" not in report
