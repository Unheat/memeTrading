"""Request, research-intent, and durable state schemas for the research agent.

Donor provenance: adapted from reference/ai-financial-research-agent/app/agent/state.py:10-35
(SimpleAgentState). The intent and candidate-isolation fields are locally written.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal, Sequence, TypedDict

from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph.message import add_messages

ResearchDepth = Literal["standard", "deep"]
_REQUESTED_RANKING_PATTERN = re.compile(r"\b(?:top|best|rank(?:ed|ing)?|compare)\s+(\d+)\b", re.IGNORECASE)


@dataclass(frozen=True)
class BudgetLimits:
    """Per-investigation execution limits.

    Args:
        max_tool_calls: Maximum tool calls the graph may execute.
        max_identical_calls: Maximum repeated identical tool signatures.

    Returns:
        Immutable budget configuration.
    """

    max_tool_calls: int = 35
    max_identical_calls: int = 2


@dataclass(frozen=True)
class ResearchIntent:
    """Prompt-derived scope that informs the model without selecting a graph route.

    Args:
        explicit_subjects: Identifiers explicitly provided by the caller.
        requested_ranking_count: Explicit ranking count parsed from the user prompt.
        requires_candidate_workspaces: Whether candidate registration is required.
        requested_position_decision: Whether the user explicitly asks for a position decision.

    Returns:
        JSON-serializable research guidance; it is not a routing profile.
    """

    explicit_subjects: tuple[str, ...] = ()
    requested_ranking_count: int | None = None
    requires_candidate_workspaces: bool = False
    requested_position_decision: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize intent for prompts and persisted case artifacts.

        Returns:
            JSON-compatible intent data.
        """
        return {
            "explicit_subjects": list(self.explicit_subjects),
            "requested_ranking_count": self.requested_ranking_count,
            "requires_candidate_workspaces": self.requires_candidate_workspaces,
            "requested_position_decision": self.requested_position_decision,
        }


@dataclass(frozen=True)
class ResearchRequest:
    """User or scheduler research direction.

    Args:
        query: Required free-form research request interpreted by the model.
        ticker: Optional explicit identifier supplied by an API caller.
        company: Optional explicit company name supplied by an API caller.
        theme: Optional research theme.
        mandate: Optional research angle.
        time_boundary: Optional as-of boundary.
        budget: Execution limits.
        template_version: Optional automation template version.
        depth: Research breadth policy.

    Returns:
        Normalized immutable request without a mode or profile.
    """

    query: str
    ticker: str | None = None
    company: str | None = None
    theme: str | None = None
    mandate: str | None = None
    time_boundary: str | None = None
    budget: BudgetLimits = field(default_factory=BudgetLimits)
    template_version: str | None = None
    depth: ResearchDepth = "deep"

    def __post_init__(self) -> None:
        """Validate input and normalize explicit identifiers.

        Raises:
            ValueError: If the prompt or depth is invalid.
        """
        if not self.query or not isinstance(self.query, str) or not self.query.strip():
            raise ValueError("query must be a non-empty string")
        if self.ticker is not None and self.ticker.strip():
            object.__setattr__(self, "ticker", self.ticker.strip().upper())
        else:
            object.__setattr__(self, "ticker", None)
        if self.depth not in {"standard", "deep"}:
            raise ValueError("depth must be standard or deep")

    def resolve_intent(self) -> ResearchIntent:
        """Extract only explicit structural constraints from the user request.

        The model determines the research plan, sources, entities, and conclusions.
        This parser exists solely to preserve an explicitly requested output count and
        to activate deterministic identity isolation for multi-candidate research.

        Returns:
            Durable prompt guidance that never chooses a graph or vetoes research.
        """
        subjects = tuple(value for value in (self.ticker, self.company) if value)
        match = _REQUESTED_RANKING_PATTERN.search(self.query)
        requested_count = int(match.group(1)) if match and int(match.group(1)) > 0 else None
        normalized = self.query.casefold()
        requires_candidates = requested_count is not None or any(
            phrase in normalized for phrase in ("compare ", "rank ", "best stocks", "best companies")
        )
        position_words = ("allocate", "position size", "buy now", "sell now", "investment recommendation")
        return ResearchIntent(
            explicit_subjects=subjects,
            requested_ranking_count=requested_count,
            requires_candidate_workspaces=requires_candidates,
            requested_position_decision=any(word in normalized for word in position_words),
        )


class InvestigationState(TypedDict):
    """Permanent structured state plus ephemeral message history for LangGraph."""

    messages: Annotated[Sequence[BaseMessage], add_messages]
    case_id: str
    depth: str
    research_intent: dict[str, Any]
    research_plan: list[dict[str, Any]]
    source_records: list[dict[str, Any]]
    claim_records: list[dict[str, Any]]
    capability_outputs: dict[str, Any]
    ticker: str
    company: str | None
    cik: str | None
    candidates: dict[str, Any]
    candidate_leads: list[dict[str, Any]]
    comparisons: list[dict[str, Any]]
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
    sec_financials: dict[str, Any] | None
    consensus_snapshot: dict[str, Any] | None
    expectation_gap: dict[str, Any] | None
    thesis_breakers: list[str]
    adversarial_report: Any | None
    bull_report: Any | None
    ic_verdict: Any | None
    budget_state: dict[str, Any]
    evidence_gate: dict[str, Any]
    accounting_gate: dict[str, Any]
    valuation_gate: dict[str, Any]
    asymmetry_gate: dict[str, Any]
    forensic_report: dict[str, Any] | None
    thematic_report: dict[str, Any] | None
    sector_report: dict[str, Any] | None
    moat_report: dict[str, Any] | None
    quant_report: dict[str, Any] | None


def create_initial_state(request: ResearchRequest, case_id: str) -> InvestigationState:
    """Initialize one universal research state from a request.

    Args:
        request: Validated research request.
        case_id: Allocated durable case identifier.

    Returns:
        Initial graph state with model-directed intent and evidence containers.
    """
    intent = request.resolve_intent()
    return {
        "messages": [HumanMessage(content=request.query)], "case_id": case_id,
        "depth": request.depth, "research_intent": intent.to_dict(),
        "research_plan": [], "source_records": [], "claim_records": [], "capability_outputs": {},
        "ticker": request.ticker or "", "company": request.company, "cik": None,
        "candidates": {}, "candidate_leads": [], "comparisons": [],
        "trigger": {"query": request.query, "theme": request.theme, "mandate": request.mandate},
        "root_claims": [], "evidence": [], "contradictions": [], "unresolved_questions": [],
        "sec_corpora": [], "searches_performed": [], "confidence": None, "tool_calls": 0,
        "status": "in_progress", "causal_chain": None, "market_context": None,
        "sec_financials": None, "consensus_snapshot": None, "expectation_gap": None,
        "thesis_breakers": [], "adversarial_report": None, "bull_report": None, "ic_verdict": None,
        "budget_state": {"max_tool_calls": request.budget.max_tool_calls,
                         "max_identical_calls": request.budget.max_identical_calls, "call_counts": {}},
        "evidence_gate": {}, "accounting_gate": {}, "valuation_gate": {}, "asymmetry_gate": {},
        "forensic_report": None, "thematic_report": None, "sector_report": None,
        "moat_report": None, "quant_report": None,
    }
