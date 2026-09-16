"""One bounded, prompt-directed LangGraph workflow for deep research."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, Sequence

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from app.agent.adversarial import run_adversarial_red_team
from app.agent.bull import run_bull_advocate
from app.agent.committee import ICVerdict, run_investment_committee
from app.agent.context import ModelContextPolicy, TokenCounter, conservative_token_counter, prepare_context
from app.agent.expectations import run_expectations_analyst
from app.agent.gate import evaluate_accounting_gate, evaluate_asymmetry_gate, evaluate_research_completeness, evaluate_valuation_gate
from app.agent.prompts import build_research_system_prompt
from app.agent.specialists import run_forensic_analysis, run_moat_analysis, run_quant_analysis, run_sector_analysis, run_thematic_analysis
from app.agent.state import InvestigationState
from app.agent.tool_result_ingestion import ingest_tool_results


def _has_evidence_gaps(state: InvestigationState) -> bool:
    """Check if multi-candidate or deep research has actionable evidence gaps."""
    candidates = state.get("candidates") or {}
    if candidates:
        if not state.get("comparisons") and len(candidates) >= 1:
            return True
        for cand in candidates.values():
            if isinstance(cand, Mapping):
                if not cand.get("market_context") or not (cand.get("sec_financials") or cand.get("sec_corpora")):
                    return True

    sources = state.get("source_records") or []
    unread_docs = [
        s for s in sources 
        if isinstance(s, Mapping) and s.get("status") == "discovered" 
        and (str(s.get("url") or "").lower().endswith(".pdf") or s.get("tool") == "read_document_discovery")
    ]
    if unread_docs:
        return True

    return False


def should_continue(state: InvestigationState) -> Literal["tools", "reflect", "next"]:
    """Route pending model tool calls or trigger deep reflection when evidence gaps exist.

    Args:
        state: Current investigation state.

    Returns:
        ``tools`` when calls remain, ``reflect`` when evidence gaps exist, otherwise ``next``.
    """
    messages = state.get("messages", [])
    tool_calls = getattr(messages[-1], "tool_calls", None) if messages else None
    budget = state.get("budget_state", {})
    max_calls = budget.get("max_tool_calls", 15)
    tool_calls_done = state.get("tool_calls", 0)

    if tool_calls:
        prior = tool_calls_done - len(tool_calls)
        return "tools" if prior < max_calls else "next"

    reflection_count = budget.get("reflection_count", 0)
    max_reflections = budget.get("max_reflection_rounds", 2)

    if tool_calls_done < max_calls and reflection_count < max_reflections and _has_evidence_gaps(state):
        return "reflect"

    return "next"


def _requires_investment_funnel(state: InvestigationState) -> bool:
    """Return whether explicit single-company position intent may enter G1--G4.

    Args:
        state: Completed collection state.

    Returns:
        True only for an explicit position request with one named target.
    """
    intent = state.get("research_intent") or {}
    return bool(intent.get("requested_position_decision")) and not bool(intent.get("requested_ranking_count")) and bool(state.get("ticker"))


def create_research_graph(
    model: Any,
    tools: Sequence[BaseTool],
    checkpointer: Any | None = None,
    context_policy: ModelContextPolicy | None = None,
    token_counter: TokenCounter = conservative_token_counter,
):
    """Compile one model-directed research loop with optional evidence-gated diligence.

    Args:
        model: Tool-capable research model.
        tools: Full research tool registry.
        checkpointer: Optional LangGraph checkpoint persistence.
        context_policy: Pair-safe context policy.
        token_counter: Context token estimator.

    Returns:
        A compiled graph used for every research request.
    """
    model_with_tools = model.bind_tools(tools) if hasattr(model, "bind_tools") else model
    policy = context_policy or ModelContextPolicy()

    def agent_node(state: InvestigationState) -> dict[str, Any]:
        """Invoke the model with prompt-derived intent and bounded context."""
        prepared = prepare_context(
            [build_research_system_prompt(state), *state.get("messages", [])],
            policy=policy,
            token_counter=token_counter,
        )
        response = model_with_tools.invoke(list(prepared.messages))
        remaining = max(0, state.get("budget_state", {}).get("max_tool_calls", 15) - state.get("tool_calls", 0))
        allowed = list(getattr(response, "tool_calls", None) or [])[:remaining]
        if isinstance(response, AIMessage) and allowed != response.tool_calls:
            response = response.model_copy(update={"tool_calls": allowed})
        return {"messages": [response], "tool_calls": state.get("tool_calls", 0) + len(allowed)}

    def ingest_node(state: InvestigationState) -> dict[str, Any]:
        """Ingest trailing tool results into durable evidence and candidate state."""
        messages = state.get("messages", [])
        start = len(messages)
        while start and isinstance(messages[start - 1], ToolMessage):
            start -= 1
        return ingest_tool_results(state, messages[start:])

    def g1(state: InvestigationState) -> dict[str, Any]:
        """Evaluate the prompt-appropriate evidence threshold."""
        outcome = evaluate_research_completeness(state)
        return {"evidence_gate": outcome, "status": outcome["status"]}

    def g2(state: InvestigationState) -> dict[str, Any]:
        """Evaluate accounting completeness for explicit investment diligence."""
        outcome = evaluate_accounting_gate(state)
        return {"accounting_gate": outcome, "status": outcome["status"]}

    def g3(state: InvestigationState) -> dict[str, Any]:
        """Evaluate valuation reproducibility for explicit investment diligence."""
        outcome = evaluate_valuation_gate(state)
        return {"valuation_gate": outcome, "status": outcome["status"]}

    def g4(state: InvestigationState) -> dict[str, Any]:
        """Evaluate deterministic asymmetry for explicit investment diligence."""
        outcome = evaluate_asymmetry_gate(state)
        return {"asymmetry_gate": outcome, "status": outcome["status"]}

    def validation_finalizer(state: InvestigationState) -> dict[str, Any]:
        """Finalize a failed diligence gate without inventing a position."""
        gate = next((item for item in (state.get("asymmetry_gate"), state.get("valuation_gate"), state.get("accounting_gate")) if item and not item.get("passed")), {})
        reason = gate.get("reason", "required validation is unavailable")
        verdict = ICVerdict(
            ticker=state.get("ticker") or "UNKNOWN",
            verdict="VALIDATION_WATCH",
            conviction_tier="VALIDATION",
            reward_to_risk_ratio=None,
            kelly_position_size_pct=0.0,
            passing_discipline_checks={"validation_gate": f"FAIL ({reason})"},
            cio_deliberation_summary=f"Validation required: {reason}. Zero capital allocated.",
        )
        return {"ic_verdict": verdict, "status": "validation_required"}

    def reflect_node(state: InvestigationState) -> dict[str, Any]:
        """Inject structured reflection prompt based on current evidence gaps."""
        candidates = state.get("candidates") or {}
        missing_cands = []
        for cid, cand in candidates.items():
            if isinstance(cand, Mapping):
                t = cand.get("ticker") or cid
                needs = []
                if not cand.get("market_context"):
                    needs.append("market data")
                if not (cand.get("sec_financials") or cand.get("sec_corpora")):
                    needs.append("SEC filings")
                if needs:
                    missing_cands.append(f"${t} ({', '.join(needs)})")

        sources = state.get("source_records") or []
        unread_docs = [
            str(s.get("url")) for s in sources 
            if isinstance(s, Mapping) and s.get("status") == "discovered" 
            and (str(s.get("url") or "").lower().endswith(".pdf") or s.get("tool") == "read_document_discovery")
        ][:5]

        budget = state.get("budget_state", {})
        remaining = max(0, budget.get("max_tool_calls", 15) - state.get("tool_calls", 0))
        ref_count = budget.get("reflection_count", 0) + 1

        prompt_lines = [
            f"### DEEP RESEARCH GAP REFLECTION (Round {ref_count})",
            f"You have {remaining} tool calls remaining.",
        ]
        if missing_cands:
            prompt_lines.append(f"- Candidates needing evidence: {', '.join(missing_cands)}")
        if unread_docs:
            prompt_lines.append(f"- Discovered document/PDF links to read with `read_document`: {', '.join(unread_docs)}")
        if not state.get("comparisons") and candidates:
            prompt_lines.append("- Call `compare_candidates` to generate cross-candidate comparison cards.")
        prompt_lines.append(
            "Dispatch follow-up tool calls (`read_document`, `search_sec_evidence`, `read_sec_evidence`, `get_ownership_and_insider_activity`, `compare_candidates`) "
            "to deepen evidence. If research is fully complete, output your final synthesis."
        )

        new_budget = dict(budget)
        new_budget["reflection_count"] = ref_count

        return {
            "messages": [HumanMessage(content="\n".join(prompt_lines))],
            "budget_state": new_budget,
        }

    workflow = StateGraph(InvestigationState)
    for name, node in {
        "agent": agent_node, "tools": ToolNode(tools), "ingest": ingest_node, "reflect": reflect_node,
        "gate_g1": g1, "q1_expectations": lambda s: run_expectations_analyst(s, model),
        "forensic": lambda s: run_forensic_analysis(s, model), "thematic": lambda s: run_thematic_analysis(s, model),
        "gate_g2": g2, "sector": lambda s: run_sector_analysis(s, model),
        "moat": lambda s: run_moat_analysis(s, model), "quant": run_quant_analysis,
        "gate_g3": g3, "bull": lambda s: run_bull_advocate(s, model),
        "bear": lambda s: run_adversarial_red_team(s, model), "gate_g4": g4,
        "committee": lambda s: run_investment_committee(s, model),
        "validation_finalizer": validation_finalizer,
    }.items():
        workflow.add_node(name, node)
    workflow.set_entry_point("agent")
    workflow.add_conditional_edges("agent", should_continue, {"tools": "tools", "reflect": "reflect", "next": "gate_g1"})
    workflow.add_edge("tools", "ingest")
    workflow.add_edge("ingest", "agent")
    workflow.add_edge("reflect", "agent")
    workflow.add_conditional_edges(
        "gate_g1",
        lambda state: "q1_expectations" if state["evidence_gate"].get("passed") and _requires_investment_funnel(state) else "end",
        {"q1_expectations": "q1_expectations", "end": END},
    )
    workflow.add_edge("q1_expectations", "forensic")
    workflow.add_edge("forensic", "thematic")
    workflow.add_edge("thematic", "gate_g2")
    workflow.add_conditional_edges("gate_g2", lambda state: "sector" if state["accounting_gate"].get("passed") else "validation_finalizer", {"sector": "sector", "validation_finalizer": "validation_finalizer"})
    workflow.add_edge("sector", "moat")
    workflow.add_edge("moat", "quant")
    workflow.add_edge("quant", "gate_g3")
    workflow.add_conditional_edges("gate_g3", lambda state: "bull" if state["valuation_gate"].get("passed") else "validation_finalizer", {"bull": "bull", "validation_finalizer": "validation_finalizer"})
    workflow.add_edge("bull", "bear")
    workflow.add_edge("bear", "gate_g4")
    workflow.add_conditional_edges("gate_g4", lambda state: "committee" if state["asymmetry_gate"].get("passed") else "validation_finalizer", {"committee": "committee", "validation_finalizer": "validation_finalizer"})
    workflow.add_edge("committee", END)
    workflow.add_edge("validation_finalizer", END)
    return workflow.compile(checkpointer=checkpointer)
