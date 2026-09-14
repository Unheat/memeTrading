"""Investigation state and request schemas for the outer research agent.

Donor provenance: adapted from reference/ai-financial-research-agent/app/agent/state.py:10-35
(SimpleAgentState) with structured forensic equity fields added.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, Any, Sequence, TypedDict
from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph.message import add_messages


@dataclass(frozen=True)
class BudgetLimits:
    """Per-investigation execution limits."""

    max_tool_calls: int = 35
    max_identical_calls: int = 2


@dataclass(frozen=True)
class ResearchRequest:
    """User or scheduler research direction."""

    query: str
    ticker: str | None = None
    company: str | None = None
    theme: str | None = None
    mandate: str | None = None
    time_boundary: str | None = None
    budget: BudgetLimits = field(default_factory=BudgetLimits)
    template_version: str | None = None

    def __post_init__(self) -> None:
        if not self.query or not isinstance(self.query, str) or not self.query.strip():
            raise ValueError("query must be a non-empty string")
        if self.ticker is not None:
            clean = self.ticker.strip().upper()
            object.__setattr__(self, "ticker", clean)


class InvestigationState(TypedDict):
    """Permanent structured state + ephemeral message history for LangGraph."""

    messages: Annotated[Sequence[BaseMessage], add_messages]
    case_id: str
    ticker: str
    company: str | None
    cik: str | None
    trigger: dict[str, Any]
    root_claims: list[str]
    evidence: list[dict[str, Any]]
    contradictions: list[dict[str, Any]]
    unresolved_questions: list[str]
    sec_corpora: list[str]
    searches_performed: list[dict[str, Any]]
    confidence: float | None
    tool_calls: int
    status: str
    causal_chain: dict[str, str] | None
    market_context: dict[str, Any] | None
    consensus_snapshot: dict[str, Any] | None
    expectation_gap: dict[str, Any] | None
    thesis_breakers: list[str]
    adversarial_report: Any | None
    ic_verdict: Any | None
    budget_state: dict[str, Any]


def create_initial_state(request: ResearchRequest, case_id: str) -> InvestigationState:
    """Initialize an InvestigationState from a ResearchRequest."""
    ticker_val = request.ticker or ""
    return {
        "messages": [HumanMessage(content=request.query)],
        "case_id": case_id,
        "ticker": ticker_val,
        "company": request.company,
        "cik": None,
        "trigger": {"query": request.query, "theme": request.theme, "mandate": request.mandate},
        "root_claims": [],
        "evidence": [],
        "contradictions": [],
        "unresolved_questions": [],
        "sec_corpora": [],
        "searches_performed": [],
        "confidence": None,
        "tool_calls": 0,
        "status": "in_progress",
        "causal_chain": None,
        "market_context": None,
        "consensus_snapshot": None,
        "expectation_gap": None,
        "thesis_breakers": [],
        "adversarial_report": None,
        "ic_verdict": None,
        "budget_state": {
            "max_tool_calls": request.budget.max_tool_calls,
            "max_identical_calls": request.budget.max_identical_calls,
            "call_counts": {},
        },
    }
