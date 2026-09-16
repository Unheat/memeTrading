"""Multi-stage, model-directed LangGraph workflow for deep research.

Donor provenance: planner and reflection supervisor concepts adapted from
LangChain Open Deep Research and GPT Researcher (skills/deep_research.py:259-378).
Local state transitions, candidate isolation, and financial accounting gates are locally written.
"""
from __future__ import annotations

import logging
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
from app.agent.gate import (
    evaluate_accounting_gate,
    evaluate_asymmetry_gate,
    evaluate_research_completeness,
    evaluate_valuation_gate,
)
from app.agent.planning import generate_research_plan, reflect_on_research_gaps, ResearchPlanSchema
from app.agent.prompts import build_research_system_prompt
from app.agent.specialists import (
    run_forensic_analysis,
    run_moat_analysis,
    run_quant_analysis,
    run_sector_analysis,
    run_thematic_analysis,
)
from app.agent.state import InvestigationState, ResearchIntent
from app.agent.tool_result_ingestion import ingest_tool_results

logger = logging.getLogger(__name__)


def _has_evidence_gaps(state: InvestigationState) -> bool:
    """Check if multi-candidate or deep research has actionable evidence gaps."""
    candidates = state.get("candidates") or {}
    if candidates:
        if not state.get("comparisons") and len(candidates) >= 1:
            return True
        for cand in candidates.values():
            if isinstance(cand, Mapping):
                if not cand.get("market_context"):
                    return True
                sec_fin = cand.get("sec_financials") or {}
                if not (
                    sec_fin.get("status") in {"ok", "ok_foreign_issuer_unstructured"}
                    or bool(sec_fin.get("periods"))
                    or cand.get("sec_corpora")
                    or cand.get("evidence")
                ):
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


def _requires_investment_funnel(state: InvestigationState) -> bool:
    """Return whether explicit single-company position intent may enter G1--G4.

    Args:
        state: Completed collection state.

    Returns:
        True only for an explicit position request with one named target.
    """
    intent = state.get("research_intent") or {}
    return (
        bool(intent.get("requested_position_decision"))
        and not bool(intent.get("requested_ranking_count"))
        and bool(state.get("ticker"))
    )


def should_continue_executor(state: InvestigationState) -> Literal["tools", "reflect", "next"]:
    """Route pending model tool calls, trigger reflection on gaps, or proceed to gates.

    Args:
        state: Current investigation state.

    Returns:
        ``tools`` when calls remain, ``reflect`` when model completed turn, otherwise ``next``.
    """
    messages = state.get("messages", [])
    tool_calls = getattr(messages[-1], "tool_calls", None) if messages else None
    budget = state.get("budget_state", {})
    max_calls = budget.get("max_tool_calls") if budget.get("max_tool_calls") is not None else budget.get("max_total_tool_calls", 35)
    tool_calls_done = state.get("tool_calls", 0)

    if tool_calls:
        prior = tool_calls_done - len(tool_calls)
        return "tools" if prior < max_calls else "next"

    reflection_count = budget.get("reflection_count", 0)
    max_reflections = budget.get("max_reflection_rounds", 2)

    if tool_calls_done < max_calls and reflection_count < max_reflections:
        return "reflect"

    return "next"


def should_continue_reflection(state: InvestigationState) -> Literal["executor", "next"]:
    """Decide whether to execute another research round based on reflection output.

    Args:
        state: State after reflection node.

    Returns:
        ``executor`` if follow-up work was proposed, else ``next`` to proceed to gate G1.
    """
    budget = state.get("budget_state", {})
    max_calls = budget.get("max_tool_calls") if budget.get("max_tool_calls") is not None else budget.get("max_total_tool_calls", 35)
    tool_calls_done = state.get("tool_calls", 0)

    if tool_calls_done >= max_calls:
        return "next"

    # If the last message is a HumanMessage injected by reflection, route back to executor
    messages = state.get("messages", [])
    if messages and isinstance(messages[-1], HumanMessage) and "DEEP RESEARCH GAP REFLECTION" in str(messages[-1].content):
        return "executor"

    return "next"


def create_research_graph(
    model: Any,
    tools: Sequence[BaseTool],
    checkpointer: Any | None = None,
    context_policy: ModelContextPolicy | None = None,
    token_counter: TokenCounter = conservative_token_counter,
):
    """Compile a multi-stage deep research graph with planning, reflection, and diligence gates.

    Args:
        model: Tool-capable research model.
        tools: Full research tool registry.
        checkpointer: Optional LangGraph checkpoint persistence.
        context_policy: Pair-safe context policy.
        token_counter: Context token estimator.

    Returns:
        Compiled StateGraph.
    """
    model_with_tools = model.bind_tools(tools) if hasattr(model, "bind_tools") else model
    policy = context_policy or ModelContextPolicy()

    def planner_node(state: InvestigationState) -> dict[str, Any]:
        """Stage 1: Generate structured ResearchPlanSchema using structured output."""
        if state.get("research_plan"):
            return {}

        query = (state.get("trigger") or {}).get("query") or (state.get("messages", [HumanMessage(content="")])[0].content)
        ticker = state.get("ticker") or None
        company = state.get("company") or None
        intent_dict = state.get("research_intent") or {}

        # For offline scripted test doubles, construct plan directly from intent without consuming mock turns
        if not hasattr(model, "with_structured_output"):
            plan = ResearchPlanSchema(
                brief=str(query),
                research_type="single_diligence" if ticker else ("multi_candidate_ranking" if intent_dict.get("requires_candidate_workspaces") else "general_deep_dive"),
                ranking_count=intent_dict.get("requested_ranking_count"),
                candidate_entities=[ticker] if ticker else [],
                requires_candidate_workspaces=bool(intent_dict.get("requires_candidate_workspaces")),
                requested_position_decision=bool(intent_dict.get("requested_position_decision")),
            )
            return {"research_plan": [plan.model_dump()]}

        try:
            plan = generate_research_plan(model, str(query), ticker=ticker, company=company)
        except Exception as exc:
            logger.warning("Structured planner failed (%s); using default plan", exc)
            plan = ResearchPlanSchema(
                brief=str(query),
                research_type="single_diligence" if ticker else ("multi_candidate_ranking" if intent_dict.get("requires_candidate_workspaces") else "general_deep_dive"),
                ranking_count=intent_dict.get("requested_ranking_count"),
                candidate_entities=[ticker] if ticker else [],
                requires_candidate_workspaces=bool(intent_dict.get("requires_candidate_workspaces")),
                requested_position_decision=bool(intent_dict.get("requested_position_decision")),
            )

        plan_dict = plan.model_dump() if hasattr(plan, "model_dump") else plan.dict()
        intent = ResearchIntent.from_plan(plan_dict, explicit_subjects=tuple(s for s in (ticker, company) if s))

        plan_summary = (
            f"**Research Plan Approved**:\n"
            f"- Mandate: {plan.brief}\n"
            f"- Type: {plan.research_type} (Ranking count: {plan.ranking_count or 'N/A'})\n"
            f"- Initial Candidates: {', '.join(plan.candidate_entities) if plan.candidate_entities else 'To be discovered'}\n"
            f"- Primary Questions:\n" + "\n".join(f"  * {q}" for q in plan.primary_questions)
        )

        return {
            "research_plan": [plan_dict],
            "research_intent": intent.to_dict(),
            "messages": [AIMessage(content=plan_summary)],
        }

    def executor_node(state: InvestigationState) -> dict[str, Any]:
        """Stage 2: Model invokes research tools guided by the active plan and candidate workspaces."""
        prepared = prepare_context(
            [build_research_system_prompt(state), *state.get("messages", [])],
            policy=policy,
            token_counter=token_counter,
        )
        response = model_with_tools.invoke(list(prepared.messages))
        budget = state.get("budget_state", {})
        max_calls = budget.get("max_tool_calls") if budget.get("max_tool_calls") is not None else budget.get("max_total_tool_calls", 35)
        remaining = max(0, max_calls - state.get("tool_calls", 0))
        allowed = list(getattr(response, "tool_calls", None) or [])[:remaining]
        if isinstance(response, AIMessage) and allowed != response.tool_calls:
            response = response.model_copy(update={"tool_calls": allowed})
        return {"messages": [response], "tool_calls": state.get("tool_calls", 0) + len(allowed)}

    def ingest_node(state: InvestigationState) -> dict[str, Any]:
        """Ingest trailing tool results into durable candidate and evidence ledgers."""
        messages = state.get("messages", [])
        start = len(messages)
        while start and isinstance(messages[start - 1], ToolMessage):
            start -= 1
        return ingest_tool_results(state, messages[start:])

    def reflection_node(state: InvestigationState) -> dict[str, Any]:
        """Stage 3: Gap analysis reflecting on collected evidence against the plan."""
        budget = state.get("budget_state", {})
        ref_count = budget.get("reflection_count", 0) + 1
        new_budget = dict(budget)
        new_budget["reflection_count"] = ref_count

        plans = state.get("research_plan") or [{}]
        plan_obj = ResearchPlanSchema(**plans[-1]) if plans[-1] else ResearchPlanSchema(brief="General research")
        candidates = state.get("candidates") or {}
        comparisons = state.get("comparisons") or []
        sources = state.get("source_records") or []
        receipts = state.get("searches_performed") or []

        reflection = None
        if hasattr(model, "with_structured_output"):
            try:
                reflection = reflect_on_research_gaps(model, plan_obj, candidates, comparisons, sources, receipts)
            except Exception as exc:
                logger.warning("Structured reflection failed (%s); using deterministic check", exc)

        # Deterministic checks
        deterministic_gaps = []
        if candidates and not comparisons and len(candidates) > 1:
            deterministic_gaps.append("Cross-candidate comparison matrix is missing; call `compare_candidates`.")
        for cid, cand in candidates.items():
            if isinstance(cand, Mapping):
                t = cand.get("ticker") or cid
                if not cand.get("market_context"):
                    deterministic_gaps.append(f"Missing market data for candidate ${t}; call `get_market_data`.")
                sec_fin = cand.get("sec_financials") or {}
                if not (
                    sec_fin.get("status") in {"ok", "ok_foreign_issuer_unstructured"}
                    or bool(sec_fin.get("periods"))
                    or cand.get("sec_corpora")
                    or cand.get("evidence")
                ):
                    deterministic_gaps.append(f"Missing SEC financial data for candidate ${t}; call `get_sec_financials` or pull filings.")

        unread_docs = [
            s.get("url")
            for s in sources
            if isinstance(s, Mapping) and s.get("status") == "discovered"
            and (str(s.get("url") or "").lower().endswith(".pdf") or s.get("tool") == "read_document_discovery")
        ]
        for url in unread_docs:
            deterministic_gaps.append(f"Unread discovered document {url}; call `read_document`.")

        all_gaps = list(deterministic_gaps)
        if reflection and reflection.evidence_gaps:
            for g in reflection.evidence_gaps:
                if g not in all_gaps:
                    all_gaps.append(g)

        is_complete = not all_gaps and (reflection.is_research_complete if reflection else True)

        max_reflections = budget.get("max_reflection_rounds", 2)
        if not is_complete and ref_count <= max_reflections:
            prompt_lines = [
                f"### DEEP RESEARCH GAP REFLECTION (Round {ref_count} of {max_reflections})",
                "The following actionable evidence gaps were identified:",
            ]
            for gap in all_gaps[:6]:
                prompt_lines.append(f"- {gap}")
            prompt_lines.append(
                "Dispatch follow-up tool calls to address these gaps. If research is fully complete, output your final synthesis."
            )
            return {
                "messages": [HumanMessage(content="\n".join(prompt_lines))],
                "budget_state": new_budget,
            }

        return {"budget_state": new_budget}

    def g1(state: InvestigationState) -> dict[str, Any]:
        """Stage 4: Evaluate the prompt-appropriate evidence threshold."""
        outcome = evaluate_research_completeness(state)
        return {"evidence_gate": outcome, "status": outcome["status"]}

    def g2(state: InvestigationState) -> dict[str, Any]:
        """Evaluate accounting completeness for explicit single-company diligence."""
        outcome = evaluate_accounting_gate(state)
        return {"accounting_gate": outcome, "status": outcome["status"]}

    def g3(state: InvestigationState) -> dict[str, Any]:
        """Evaluate valuation reproducibility for explicit single-company diligence."""
        outcome = evaluate_valuation_gate(state)
        return {"valuation_gate": outcome, "status": outcome["status"]}

    def g4(state: InvestigationState) -> dict[str, Any]:
        """Evaluate deterministic asymmetry for explicit single-company diligence."""
        outcome = evaluate_asymmetry_gate(state)
        return {"asymmetry_gate": outcome, "status": outcome["status"]}

    def validation_finalizer(state: InvestigationState) -> dict[str, Any]:
        """Finalize a failed diligence gate without inventing a position."""
        gate = next(
            (
                item
                for item in (state.get("asymmetry_gate"), state.get("valuation_gate"), state.get("accounting_gate"))
                if item and not item.get("passed")
            ),
            {},
        )
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

    workflow = StateGraph(InvestigationState)
    for name, node in {
        "planner": planner_node,
        "executor": executor_node,
        "tools": ToolNode(tools),
        "ingest": ingest_node,
        "reflect": reflection_node,
        "gate_g1": g1,
        "q1_expectations": lambda s: run_expectations_analyst(s, model),
        "forensic": lambda s: run_forensic_analysis(s, model),
        "thematic": lambda s: run_thematic_analysis(s, model),
        "gate_g2": g2,
        "sector": lambda s: run_sector_analysis(s, model),
        "moat": lambda s: run_moat_analysis(s, model),
        "quant": run_quant_analysis,
        "gate_g3": g3,
        "bull": lambda s: run_bull_advocate(s, model),
        "bear": lambda s: run_adversarial_red_team(s, model),
        "gate_g4": g4,
        "committee": lambda s: run_investment_committee(s, model),
        "validation_finalizer": validation_finalizer,
    }.items():
        workflow.add_node(name, node)

    # Workflow entry point is the structured planner
    workflow.set_entry_point("planner")
    workflow.add_edge("planner", "executor")

    # Dynamic execution loop with tools, ingest, and reflection
    workflow.add_conditional_edges(
        "executor",
        should_continue_executor,
        {"tools": "tools", "reflect": "reflect", "next": "gate_g1"},
    )
    workflow.add_edge("tools", "ingest")
    workflow.add_edge("ingest", "executor")

    workflow.add_conditional_edges(
        "reflect",
        should_continue_reflection,
        {"executor": "executor", "next": "gate_g1"},
    )

    # Gate G1 routing
    workflow.add_conditional_edges(
        "gate_g1",
        lambda state: "q1_expectations" if state["evidence_gate"].get("passed") and _requires_investment_funnel(state) else "end",
        {"q1_expectations": "q1_expectations", "end": END},
    )

    # Diligence pipeline for single-company investment decisions
    workflow.add_edge("q1_expectations", "forensic")
    workflow.add_edge("forensic", "thematic")
    workflow.add_edge("thematic", "gate_g2")
    workflow.add_conditional_edges(
        "gate_g2",
        lambda state: "sector" if state["accounting_gate"].get("passed") else "validation_finalizer",
        {"sector": "sector", "validation_finalizer": "validation_finalizer"},
    )
    workflow.add_edge("sector", "moat")
    workflow.add_edge("moat", "quant")
    workflow.add_edge("quant", "gate_g3")
    workflow.add_conditional_edges(
        "gate_g3",
        lambda state: "bull" if state["valuation_gate"].get("passed") else "validation_finalizer",
        {"bull": "bull", "validation_finalizer": "validation_finalizer"},
    )
    workflow.add_edge("bull", "bear")
    workflow.add_edge("bear", "gate_g4")
    workflow.add_conditional_edges(
        "gate_g4",
        lambda state: "committee" if state["asymmetry_gate"].get("passed") else "validation_finalizer",
        {"committee": "committee", "validation_finalizer": "validation_finalizer"},
    )
    workflow.add_edge("committee", END)
    workflow.add_edge("validation_finalizer", END)

    return workflow.compile(checkpointer=checkpointer)
