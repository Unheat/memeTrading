"""Multi-stage, model-directed LangGraph workflow for universal deep research.

Donor provenance: planner and reflection supervisor concepts adapted from
LangChain Open Deep Research and GPT Researcher (skills/deep_research.py:259-378).
Specialist lenses (expectations, forensic accounting, moat, quant valuation via calculator.mjs,
bull/bear adversarial debate, and committee deliberation) are adapted from
reference/investment-research and reference/ai-hedge-fund.
All stages execute continuously and gracefully without abort tripwires.
"""
from __future__ import annotations

import json
import logging
import math
from collections.abc import Mapping
from typing import Any, Literal, Sequence

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from app.agent.adversarial import AdversarialReport
from app.agent.bull import BullReport
from app.agent.committee import run_investment_committee
from app.agent.context import ModelContextPolicy, TokenCounter, conservative_token_counter, prepare_context
from app.agent.gate import (
    evaluate_accounting_gate,
    evaluate_asymmetry_gate,
    evaluate_research_completeness,
    evaluate_valuation_gate,
    has_candidate_sec_evidence,
)
from app.agent.ledger import ResearchWorkItem
from app.agent.planning import (
    assess_scout_need,
    build_deterministic_shortlist,
    generate_research_plan,
    reflect_on_research_gaps,
    ResearchPlanSchema,
)
from app.agent.prompts import build_research_system_prompt
from app.agent.state import InvestigationState, ResearchIntent
from app.agent.tool_result_ingestion import ingest_tool_results

logger = logging.getLogger(__name__)


def _is_issuer_pdf(source: Mapping[str, Any], active_candidate_ids: set[str]) -> bool:
    """Decide whether a discovered source is an issuer-relevant unread PDF.

    A PDF is issuer-relevant when it is an SEC.gov document or when its source record
    is bound to an active candidate workspace. Junk PDFs from unrelated domains are
    excluded so reflection never spends tool budget reading them.

    Args:
        source: Source record dict (url, status, candidate_id).
        active_candidate_ids: Ids of candidates not vetoed/screened out.

    Returns:
        True when the record is a discovered PDF worth flagging.
    """
    if str(source.get("status") or "") != "discovered":
        return False
    url = str(source.get("url") or "").lower()
    if not url.endswith(".pdf"):
        return False
    return "sec.gov" in url or str(source.get("candidate_id") or "") in active_candidate_ids


def _has_evidence_gaps(state: InvestigationState) -> bool:
    """Check if multi-candidate or deep research has actionable evidence gaps."""
    candidates = state.get("candidates") or {}
    if candidates:
        active_candidates = [
            c for c in candidates.values()
            if isinstance(c, Mapping)
            and c.get("status") not in {"vetoed", "rejected", "screened_out"}
            and not c.get("veto_reason")
        ]
        equity_candidates = [c for c in active_candidates if c.get("ticker")]
        if len(equity_candidates) > 1 and not state.get("comparisons"):
            return True

        for cand in active_candidates:
            if not cand.get("ticker"):
                continue
            if not cand.get("market_context"):
                return True
            if not has_candidate_sec_evidence(cand):
                return True
            if not (cand.get("diligence_dossier") or cand.get("valuation") or cand.get("quant_report")):
                return True

    sources = state.get("source_records") or []
    active_candidate_ids = {
        str(candidate_id)
        for candidate_id, candidate in candidates.items()
        if isinstance(candidate, Mapping)
        and candidate.get("status") not in {"vetoed", "rejected", "screened_out"}
        and not candidate.get("veto_reason")
    }
    unread_pdfs = [
        source for source in sources
        if isinstance(source, Mapping) and _is_issuer_pdf(source, active_candidate_ids)
    ]
    if unread_pdfs:
        return True

    open_items = [
        w for w in (state.get("work_queue") or [])
        if isinstance(w, Mapping) and w.get("status") == "queued"
    ]
    if open_items:
        return True

    return False


def should_continue_executor(state: InvestigationState) -> Literal["tools", "reflect", "committee"]:
    """Route pending model tool calls, trigger reflection on gaps, or proceed to committee.

    Args:
        state: Current investigation state.

    Returns:
        ``tools`` when calls remain, ``reflect`` when model completed turn, otherwise ``committee``.
    """
    messages = state.get("messages", [])
    tool_calls = getattr(messages[-1], "tool_calls", None) if messages else None
    budget = state.get("budget_state", {})
    max_calls = budget.get("max_tool_calls") if budget.get("max_tool_calls") is not None else budget.get("max_total_tool_calls", 50)
    tool_calls_done = state.get("tool_calls", 0)

    if tool_calls:
        prior = tool_calls_done - len(tool_calls)
        return "tools" if prior < max_calls else "committee"

    reflection_count = budget.get("reflection_count", 0)
    max_reflections = budget.get("max_reflection_rounds", 2)

    if tool_calls_done < max_calls and reflection_count < max_reflections:
        return "reflect"

    return "committee"


def should_continue_reflection(state: InvestigationState) -> Literal["executor", "committee"]:
    """Decide whether to execute another research round based on reflection output.

    Args:
        state: State after reflection node.

    Returns:
        ``executor`` if follow-up work was proposed, else ``committee`` to proceed forward.
    """
    budget = state.get("budget_state", {})
    max_calls = budget.get("max_tool_calls") if budget.get("max_tool_calls") is not None else budget.get("max_total_tool_calls", 50)
    tool_calls_done = state.get("tool_calls", 0)

    if tool_calls_done >= max_calls:
        return "committee"

    messages = state.get("messages", [])
    if messages and isinstance(messages[-1], HumanMessage) and "DEEP RESEARCH GAP REFLECTION" in str(messages[-1].content):
        return "executor"

    return "committee"


def _extract_callback_handler(config: Any) -> Any:
    """Extract InvestigationCallbackHandler from execution config if present."""
    if not config:
        return None
    callbacks = config.get("callbacks") if isinstance(config, dict) else getattr(config, "callbacks", None)
    if callbacks is None:
        return None

    if hasattr(callbacks, "handlers"):
        # CallbackManager instance carries a .handlers list of actual handlers
        candidates = list(callbacks.handlers)
    elif isinstance(callbacks, (list, tuple)):
        candidates = list(callbacks)
    else:
        candidates = [callbacks]

    for cb in candidates:
        if hasattr(cb, "set_stage"):
            return cb
    return None


def create_research_graph(
    model: Any,
    tools: Sequence[BaseTool],
    checkpointer: Any | None = None,
    context_policy: ModelContextPolicy | None = None,
    token_counter: TokenCounter = conservative_token_counter,
):
    """Compile a multi-stage deep research graph with planning, reflection, and non-blocking specialist lenses.

    Args:
        model: Tool-capable research model.
        tools: Full research tool registry.
        checkpointer: Optional LangGraph checkpoint persistence.
        context_policy: Pair-safe context policy.
        token_counter: Context token estimator.

    Returns:
        Compiled StateGraph with continuous, non-blocking flow.
    """
    model_with_tools = model.bind_tools(tools) if hasattr(model, "bind_tools") else model
    policy = context_policy or ModelContextPolicy()

    def planner_node(state: InvestigationState, config: RunnableConfig = None) -> dict[str, Any]:
        """Stage 1: Generate structured ResearchPlanSchema using structured output and scout intelligence."""
        if state.get("research_plan"):
            return {}

        cb = _extract_callback_handler(config)
        query = (state.get("trigger") or {}).get("query") or (state.get("messages", [HumanMessage(content="")])[0].content)
        ticker = state.get("ticker") or None
        company = state.get("company") or None
        intent_dict = state.get("research_intent") or {}
        as_of = state.get("as_of_date")

        # Stage 1a: Model-driven preliminary discovery scouting (wide net)
        scout_context = ""
        tool_map = {getattr(t, "name", ""): t for t in tools}
        if str(query).strip() and not ticker and not company:
            try:
                if cb:
                    cb.set_stage("planner")
                    cb.emit_stage("planner", "Stage 1 — Scout Assessment & Discovery (Tavily/Screener/Social)")
                assessment = assess_scout_need(model, str(query), ticker=ticker, company=company)
                if assessment.needs_scouting and assessment.scout_queries:
                    lines = []
                    screen_rows: list[dict[str, Any]] = []
                    for sq in assessment.scout_queries[:4]:
                        tool_to_use = (
                            tool_map.get(sq.tool_name)
                            or tool_map.get("screen_stocks")
                            or tool_map.get("search_web")
                            or tool_map.get("search_articles")
                        )
                        if not tool_to_use:
                            continue
                        try:
                            if getattr(sq, "tool_name", "") == "screen_stocks" and hasattr(tool_to_use, "invoke"):
                                tool_args = {
                                    "preset": getattr(sq, "preset", None),
                                    "sector": getattr(sq, "sector", None) or (getattr(sq, "query", None) if not getattr(sq, "preset", None) else None),
                                    "limit": min(max(int(getattr(sq, "limit", 20) or 20), 1), 20),
                                }
                            else:
                                tool_args = {
                                    "query": str(getattr(sq, "query", ""))[:180],
                                    "limit": min(max(int(getattr(sq, "limit", 10) or 10), 1), 10),
                                }

                            raw_out = tool_to_use.invoke(tool_args)
                            if not raw_out:
                                continue
                            data = json.loads(raw_out) if isinstance(raw_out, str) else raw_out
                            items = (
                                data.get("records", [])
                                or data.get("articles", [])
                                or data.get("results", [])
                                or data.get("posts", [])
                            )
                            for item in items:
                                if not isinstance(item, dict):
                                    continue
                                if sq.tool_name == "screen_stocks" and item.get("ticker"):
                                    screen_rows.append(item)
                                    continue
                                t_str = item.get("title") or item.get("ticker") or ""
                                s_str = item.get("summary") or item.get("snippet") or item.get("text") or ""
                                if not s_str and item.get("company"):
                                    s_str = f"{item.get('company')} - Market Cap: {item.get('market_cap')}"
                                if t_str or s_str:
                                    lines.append(f"- {t_str}: {s_str}")
                        except Exception as sub_exc:
                            logger.debug("Scout tool %s query '%s' failed: %s", sq.tool_name, sq.query, sub_exc)

                    context_blocks: list[str] = []

                    # Deterministic first cut: rank the full screener pool in code,
                    # so deep-dive candidates come from a wide net, not a 5-row glance.
                    if screen_rows:
                        # Elastic shortlist ceiling scaling logarithmically with tool budget
                        shortlist_limit = min(15, max(5, int(2.5 * math.log(max(max_calls, 10)))))
                        shortlist = build_deterministic_shortlist(screen_rows, top_n=shortlist_limit)
                        if shortlist:
                            shortlist_lines = [
                                f"{idx}. ${r['ticker']} — composite {r['composite_score']:.2f} "
                                f"(value {r['value_score']:.2f}, quality {r['quality_score']:.2f}, "
                                f"momentum {r['momentum_score']:.2f}, size {r['size_score']:.2f}) | Cap ${r['market_cap'] / 1e9:.1f}B | "
                                f"Fwd P/E {r['forward_pe'] if r['forward_pe'] is not None else r['trailing_pe']} | "
                                f"Consensus {r['analyst_rating'] or 'n/a'}"
                                for idx, r in enumerate(shortlist, 1)
                            ]
                            context_blocks.append(
                                "### Deterministic Screening Shortlist (ranked by code from "
                                f"{len(screen_rows)} live screener rows — the first cut is deterministic, not model opinion)\n"
                                + "\n".join(shortlist_lines)
                            )
                            if cb:
                                cb.emit(
                                    event_type="gate",
                                    title=f"Deterministic shortlist cut: {len(screen_rows)} screened → {len(shortlist)} shortlisted",
                                    payload={
                                        "screened": len(screen_rows),
                                        "shortlisted": [r["ticker"] for r in shortlist],
                                    },
                                )
                            logger.info(
                                "pipeline.planner_shortlist screened=%d shortlist=%s",
                                len(screen_rows), [r["ticker"] for r in shortlist],
                            )

                    if lines:
                        context_blocks.append(
                            "### Web & News Discovery Leads (tickers the screener cannot express)\n"
                            + "\n".join(lines[:8])
                        )

                    if context_blocks:
                        scout_context = "\n\n".join(context_blocks)
                        scout_context += (
                            "\n\nCONSTRAINT: candidate_entities MUST be selected from the Deterministic "
                            "Screening Shortlist and/or the Web & News Discovery Leads above "
                            "(unless the user explicitly named tickers in the request)."
                        )
                        logger.info("pipeline.planner_scout_obtained screen_rows=%d lead_lines=%d", len(screen_rows), len(lines[:8]))
            except Exception as exc:
                logger.debug("Preliminary scout assessment failed (%s); proceeding with ungrounded planning", exc)

        budget_dict = state.get("budget_state") or {}
        max_calls = budget_dict.get("max_total_tool_calls") or budget_dict.get("max_tool_calls", 50)

        if cb:
            cb.set_stage("planner")
            cb.emit_stage("planner", "Stage 1 — Plan Synthesis & Candidate Workspace Hydration")

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
            plan = generate_research_plan(
                model,
                str(query),
                ticker=ticker,
                company=company,
                scout_context=scout_context,
                as_of_date=as_of,
                max_tool_calls=max_calls,
            )
        except Exception as exc:
            logger.warning("Structured planner failed (%s); using fallback plan", exc)
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

        # Logarithmic candidate envelope k_max(B): prevents breadth explosion on large budgets
        if ticker:
            max_candidates_allowed = 1
        else:
            log_bound = max(2, int(1 + 1.8 * math.log(max(max_calls, 10))))
            req_count = plan.ranking_count or intent_dict.get("requested_ranking_count")
            max_candidates_allowed = min(req_count, log_bound) if req_count else log_bound
            max_candidates_allowed = min(8, max_candidates_allowed)

        # Extract tier allocations from plan if supplied
        tier_allocations: dict[str, str] = {}
        for alloc in getattr(plan, "candidate_allocations", []) or []:
            if isinstance(alloc, Mapping):
                t = str(alloc.get("ticker") or "").strip().upper()
                if t:
                    tier_allocations[t] = str(alloc.get("priority") or "tier1_deep")
            elif hasattr(alloc, "ticker"):
                t = str(alloc.ticker or "").strip().upper()
                if t:
                    tier_allocations[t] = str(getattr(alloc, "priority", "tier1_deep"))

        # Auto-seed candidate workspaces to prevent entity_conflict on early tool calls,
        # capped by the elastic candidate envelope k_max(B).
        seeded_candidates = dict(state.get("candidates") or {})
        candidate_list = list(plan.candidate_entities or [])[:max_candidates_allowed]
        for idx, c_ticker in enumerate(candidate_list):
            clean_c = c_ticker.strip().upper()
            cid = f"cand_{clean_c.lower()}"
            alloc_tier = tier_allocations.get(clean_c) or ("tier1_deep" if idx < 3 else "tier2_light")
            if cid not in seeded_candidates:
                seeded_candidates[cid] = {
                    "candidate_id": cid,
                    "ticker": clean_c,
                    "company": "",
                    "diligence_tier": alloc_tier,
                    "sec_corpora": [],
                    "evidence": [],
                    "contradictions": [],
                    "fact_cards": [],
                    "status": "discovered",
                }
        if ticker:
            clean_t = ticker.strip().upper()
            cid = f"cand_{clean_t.lower()}"
            if cid not in seeded_candidates:
                seeded_candidates[cid] = {
                    "candidate_id": cid,
                    "ticker": clean_t,
                    "company": str(company or ""),
                    "diligence_tier": "tier1_deep",
                    "sec_corpora": [],
                    "evidence": [],
                    "contradictions": [],
                    "fact_cards": [],
                    "status": "discovered",
                }

        work_items = []
        is_equity = bool(ticker or company or plan.candidate_entities)
        if getattr(plan, "hypotheses", None):
            for idx, hyp in enumerate(plan.hypotheses, start=1):
                c_id = f"cand_{hyp.target_entity.strip().lower()}" if hyp.target_entity else None
                item = ResearchWorkItem(
                    work_id=f"work_hyp_{idx}",
                    question=hyp.statement,
                    evidence_tier=hyp.evidence_tier,
                    priority=10 - idx,
                    depth=1,
                    candidate_id=c_id,
                )
                work_items.append(item.to_dict())
        else:
            for idx, q in enumerate(plan.primary_questions or [], start=1):
                tier = "primary_sec" if is_equity else "general"
                item = ResearchWorkItem(
                    work_id=f"work_q_{idx}",
                    question=q,
                    evidence_tier=tier,
                    priority=10 - idx,
                    depth=1,
                )
                work_items.append(item.to_dict())

        for c_idx, c_ticker in enumerate(plan.candidate_entities or [], start=1):
            clean_c = c_ticker.strip().upper()
            item = ResearchWorkItem(
                work_id=f"work_cand_{clean_c.lower()}",
                question=f"Conduct candidate diligence and valuation for {clean_c}",
                evidence_tier="candidate_diligence",
                priority=8,
                depth=1,
                candidate_id=f"cand_{clean_c.lower()}",
            )
            work_items.append(item.to_dict())

        plan_summary = (
            f"**Research Plan Approved**:\n"
            f"- Mandate: {plan.brief}\n"
            f"- Type: {plan.research_type} (Ranking count: {plan.ranking_count or 'N/A'})\n"
            f"- Initial Candidates: {', '.join(plan.candidate_entities) if plan.candidate_entities else 'To be discovered'}\n"
            f"- Primary Questions:\n" + "\n".join(f"  * {q}" for q in plan.primary_questions)
        )

        logger.info(
            "pipeline.planner_complete type=%s candidates=%s questions=%s work_items=%s",
            plan.research_type, len(plan.candidate_entities), len(plan.primary_questions), len(work_items),
        )
        return {
            "research_plan": [plan_dict],
            "research_intent": intent.to_dict(),
            "work_queue": work_items,
            "candidates": seeded_candidates,
            "messages": [
                AIMessage(content=plan_summary),
                HumanMessage(content="Execute the deep research plan using your available tools. Select high-priority investigations to begin."),
            ],
        }

    def executor_node(state: InvestigationState, config: RunnableConfig = None) -> dict[str, Any]:
        """Stage 2: Model invokes research tools guided by the active plan and candidate workspaces."""
        cb = _extract_callback_handler(config)
        turn_num = (state.get("tool_calls", 0) // 5) + 1
        if cb:
            cb.set_stage("executor")
            cb.emit_stage("executor", f"Stage 2 — Deep Research Agent Loop: Turn {turn_num}")

        prepared = prepare_context(
            [build_research_system_prompt(state), *state.get("messages", [])],
            policy=policy,
            token_counter=token_counter,
        )
        response = model_with_tools.invoke(list(prepared.messages))
        budget = state.get("budget_state", {})
        max_calls = budget.get("max_tool_calls") if budget.get("max_tool_calls") is not None else budget.get("max_total_tool_calls", 50)
        remaining = max(0, max_calls - state.get("tool_calls", 0))
        allowed = list(getattr(response, "tool_calls", None) or [])[:remaining]
        if isinstance(response, AIMessage) and allowed != response.tool_calls:
            response = response.model_copy(update={"tool_calls": allowed})
        logger.info(
            "pipeline.executor_turn tool_calls_requested=%s tool_calls_admitted=%s total_after=%s",
            [call.get("name") for call in getattr(response, "tool_calls", []) or []], len(allowed), state.get("tool_calls", 0) + len(allowed),
        )
        return {"messages": [response], "tool_calls": state.get("tool_calls", 0) + len(allowed)}

    def ingest_node(state: InvestigationState, config: RunnableConfig = None) -> dict[str, Any]:
        """Ingest trailing tool results into durable candidate and evidence ledgers."""
        cb = _extract_callback_handler(config)
        if cb:
            cb.set_stage("ingest")

        messages = state.get("messages", [])
        start = len(messages)
        while start and isinstance(messages[start - 1], ToolMessage):
            start -= 1
        updates = ingest_tool_results(state, messages[start:])

        # Advance work queue items based on tool results and candidate progress
        work_queue = list(state.get("work_queue") or [])
        if work_queue:
            performed = state.get("searches_performed") or []
            tool_names = {r.get("tool") for r in performed if r.get("status") in {"ok", "partial"}}
            cand_diligence_done = set()
            vetoed_cand_ids = set()
            for cid, c in (state.get("candidates") or {}).items():
                if isinstance(c, Mapping):
                    t = c.get("ticker") or (c.get("diligence_dossier") or {}).get("ticker")
                    if c.get("diligence_dossier") or c.get("valuation") or c.get("quant_report"):
                        if t:
                            cand_diligence_done.add(str(t).upper())
                    if c.get("status") in {"vetoed", "rejected", "screened_out"} or c.get("veto_reason"):
                        if t:
                            vetoed_cand_ids.add(str(t).upper())
                        vetoed_cand_ids.add(str(cid).upper())

            updated_queue = []
            for item in work_queue:
                w = dict(item)
                if w.get("status") == "queued":
                    c_id = w.get("candidate_id") or ""
                    clean_cid = str(c_id).upper().strip()
                    cid_ticker = clean_cid.removeprefix("WORK_CAND_").removeprefix("CAND_")
                    is_done = (
                        cid_ticker in cand_diligence_done
                        or clean_cid in cand_diligence_done
                        or c_id in cand_diligence_done
                        or cid_ticker in vetoed_cand_ids
                        or clean_cid in vetoed_cand_ids
                        or c_id in vetoed_cand_ids
                    )
                    if c_id and is_done:
                        w["status"] = "completed"
                    elif w.get("evidence_tier") == "primary_sec" and ("get_sec_financials" in tool_names or "search_sec_evidence" in tool_names):
                        w["status"] = "completed"
                    elif (len(state.get("evidence") or []) >= 2 or len(state.get("source_records") or []) >= 2 or len(updates.get("source_records") or []) >= 2) and w.get("evidence_tier") == "general":
                        w["status"] = "completed"
                updated_queue.append(w)
            updates["work_queue"] = updated_queue

        logger.info(
            "pipeline.ingest_complete receipts=%s candidates=%s candidate_market=%s candidate_sec=%s",
            len(updates.get("searches_performed") or []), len(updates.get("candidates") or {}),
            [cid for cid, cand in (updates.get("candidates") or {}).items() if isinstance(cand, Mapping) and cand.get("market_context")],
            [cid for cid, cand in (updates.get("candidates") or {}).items() if isinstance(cand, Mapping) and cand.get("sec_financials")],
        )
        return updates

    def reflection_node(state: InvestigationState, config: RunnableConfig = None) -> dict[str, Any]:
        """Stage 3: Gap analysis reflecting on collected evidence against the plan."""
        cb = _extract_callback_handler(config)
        budget = state.get("budget_state", {})
        ref_count = budget.get("reflection_count", 0) + 1
        new_budget = dict(budget)
        new_budget["reflection_count"] = ref_count

        if cb:
            cb.set_stage("reflect")
            cb.emit_stage("reflect", f"Stage 4 — Gap Reflection (Round {ref_count})")

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

        deterministic_gaps = []
        active_candidates = [
            c for c in candidates.values()
            if isinstance(c, Mapping)
            and c.get("status") not in {"vetoed", "rejected", "screened_out"}
            and not c.get("veto_reason")
        ]
        equity_candidates = [c for c in active_candidates if c.get("ticker")]
        if len(equity_candidates) > 1 and not comparisons:
            deterministic_gaps.append("Cross-candidate comparison matrix is missing; call `compare_candidates`.")
        for cid, cand in candidates.items():
            if isinstance(cand, Mapping):
                if cand.get("status") in {"vetoed", "rejected", "screened_out"} or cand.get("veto_reason"):
                    continue
                t = cand.get("ticker")
                if not t:
                    continue
                if not cand.get("market_context"):
                    deterministic_gaps.append(f"Missing market data for candidate ${t}; call `get_market_data`.")
                sec_fin = cand.get("sec_financials") or {}
                fin_status = sec_fin.get("status")
                has_financial_coverage = (
                    fin_status in {"ok", "ok_foreign_issuer_unstructured"}
                    or bool(sec_fin.get("periods"))
                    or bool(cand.get("sec_corpora"))
                    or bool(cand.get("evidence"))
                    or (fin_status == "unavailable" and bool(cand.get("fact_cards") or cand.get("market_context")))
                )
                if not has_financial_coverage:
                    deterministic_gaps.append(f"Missing SEC financial data for candidate ${t}; call `get_sec_financials` or pull filings.")
                if not (cand.get("diligence_dossier") or cand.get("valuation") or cand.get("quant_report")):
                    deterministic_gaps.append(
                        f"Candidate ${t} lacks valuation and Red Team stress testing; call `conduct_candidate_diligence` or `evaluate_valuation` (or veto candidate if uninvestable)."
                    )

        # Fix 9 (audit 2026-09-26): only issuer-relevant PDFs are suggested as unread —
        # SEC.gov documents or source records attached to an active candidate workspace.
        # Unfiltered discovery previously demanded reading irrelevant government PDFs.
        active_candidate_ids = {
            cid for cid, c in candidates.items()
            if isinstance(c, Mapping)
            and c.get("status") not in {"vetoed", "rejected", "screened_out"}
            and not c.get("veto_reason")
        }
        unread_pdfs = [
            str(s.get("url"))
            for s in sources
            if isinstance(s, Mapping) and _is_issuer_pdf(s, active_candidate_ids)
        ]
        for url in unread_pdfs[:1]:
            deterministic_gaps.append(f"Unread financial/earnings PDF {url}; call `read_document` if needed.")

        open_items = [w.get("question") for w in (state.get("work_queue") or []) if isinstance(w, Mapping) and w.get("status") == "queued"]
        for q in open_items[:2]:
            deterministic_gaps.append(f"Unresolved research mandate: {q}")

        all_gaps = list(deterministic_gaps)
        if reflection and reflection.evidence_gaps:
            for g in reflection.evidence_gaps:
                if g not in all_gaps:
                    all_gaps.append(g)

        core_gaps_exist = _has_evidence_gaps(state)
        is_complete = not core_gaps_exist and (reflection.is_research_complete if reflection else True)
        max_reflections = budget.get("max_reflection_rounds", 2)
        logger.info(
            "pipeline.reflection round=%s complete=%s gaps=%s open_work_items=%s",
            ref_count, is_complete, all_gaps[:6], len(open_items),
        )
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

    def diligence_node(state: InvestigationState, config: RunnableConfig = None) -> dict[str, Any]:
        """Execute diligence lenses and committee deliberation if evidence passed."""
        cb = _extract_callback_handler(config)
        if cb:
            cb.set_stage("diligence")
            cb.emit_stage("diligence", "Stage 5 — Governance Gates & Investment Committee (The Boardroom)")

        outcome = evaluate_research_completeness(state)
        updates: dict[str, Any] = {"evidence_gate": outcome, "status": outcome["status"]}

        # If evidence gate failed on an explicit position recommendation, stop before decision stages
        if not outcome["passed"] and (state.get("research_intent") or {}).get("requested_position_decision"):
            return updates

        ticker = state.get("ticker")
        candidates = state.get("candidates") or {}
        intent_dict = state.get("research_intent") or {}
        is_multi_candidate = bool(intent_dict.get("requires_candidate_workspaces"))

        chosen_candidate = None

        if ticker and ticker != "UNKNOWN" and candidates:
            for cid, c in candidates.items():
                if isinstance(c, Mapping) and str(c.get("ticker") or "").upper() == str(ticker).upper():
                    chosen_candidate = c
                    break

        # Only promote a single candidate if NOT a multi-candidate workspace or if exactly one candidate exists
        if not chosen_candidate and candidates and (not is_multi_candidate or len(candidates) == 1):
            best_cand = None
            best_ratio = -float("inf")
            for cid, c in candidates.items():
                if isinstance(c, Mapping):
                    is_vetoed = c.get("status") in {"vetoed", "rejected", "screened_out"} or bool(c.get("veto_reason"))
                    dossier = c.get("diligence_dossier")
                    if dossier and isinstance(dossier, Mapping) and not is_vetoed:
                        ratio = (dossier.get("valuation") or {}).get("reward_to_risk_ratio")
                        r_val = float(ratio) if ratio is not None else 0.0
                        if best_cand is None or r_val > best_ratio:
                            best_cand = c
                            best_ratio = r_val
                    elif best_cand is None and c.get("ticker") and not is_vetoed:
                        best_cand = c
            chosen_candidate = best_cand or next((c for c in candidates.values() if isinstance(c, Mapping)), None)

        # Promote chosen candidate workspace ONLY in single-stock mode
        if chosen_candidate and (not is_multi_candidate or len(candidates) == 1):
            c_ticker = str(
                chosen_candidate.get("ticker")
                or (chosen_candidate.get("diligence_dossier") or {}).get("ticker")
                or ""
            ).upper()
            if c_ticker:
                ticker = c_ticker
                updates["ticker"] = ticker
            if chosen_candidate.get("company"):
                updates["company"] = chosen_candidate["company"]
            if chosen_candidate.get("cik"):
                updates["cik"] = chosen_candidate["cik"]

            dossier = chosen_candidate.get("diligence_dossier") or {}
            val = dossier.get("valuation") or {}
            ratio = val.get("reward_to_risk_ratio")
            repro_verdict = val.get("reproducibility") or "pass"

            if not state.get("forensic_report") and (dossier.get("forensic_verdict") or chosen_candidate.get("forensic_report")):
                updates["forensic_report"] = chosen_candidate.get("forensic_report") or {
                    "status": "available",
                    "verdict": dossier.get("forensic_verdict") or "QUALIFIED_NORMALIZED_ADJUSTMENT",
                    "source": "candidate_diligence_dossier",
                }

            if not state.get("quant_report") and (val.get("fair_value") is not None or val.get("implied_growth_rate") is not None or chosen_candidate.get("quant_report")):
                updates["quant_report"] = chosen_candidate.get("quant_report") or {
                    "status": "available" if repro_verdict == "pass" else "validation_error",
                    "reproducibility": {
                        "status": "ok",
                        "result": {"verdict": repro_verdict},
                    },
                    "valuation": {
                        "fair_value": val.get("fair_value"),
                        "fair_value_range": val.get("fair_value_range"),
                        "implied_fcf_growth_rate": val.get("implied_growth_rate"),
                        "asymmetric_risk_reward": {
                            "reward_to_risk_ratio": ratio,
                            "qualifies_3_to_1": bool(ratio is not None and ratio >= 3.0),
                        },
                    },
                }

            if not state.get("bull_report") and (dossier.get("bull_catalysts") or dossier.get("bull_thesis")):
                updates["bull_report"] = BullReport(
                    ticker=ticker,
                    catalysts=tuple(dossier.get("bull_catalysts") or ()),
                    operating_leverage_drivers=(),
                    bull_target_price=dossier.get("bull_target_price") or val.get("fair_value"),
                    bull_thesis_summary=dossier.get("bull_thesis") or "",
                    invalidation_conditions=(),
                    status=str(dossier.get("bull_report_status") or "available"),
                )

            if not state.get("moat_report") and dossier.get("moat_report"):
                updates["moat_report"] = dossier.get("moat_report")

            if not state.get("adversarial_report") and (dossier.get("bear_kill_triggers") or dossier.get("bear_thesis") or dossier.get("bear_floor") is not None):
                updates["adversarial_report"] = AdversarialReport(
                    ticker=ticker,
                    falsifiable_objections=(),
                    numeric_kill_criteria=tuple(dossier.get("bear_kill_triggers") or ()),
                    bear_floor_price=dossier.get("bear_floor"),
                    bear_thesis_summary=dossier.get("bear_thesis") or "",
                )
                updates["thesis_breakers"] = list(dossier.get("bear_kill_triggers") or ())

            if not state.get("expectation_gap") and (dossier.get("expectation_gap") or chosen_candidate.get("expectation_gap")):
                updates["expectation_gap"] = dossier.get("expectation_gap") or chosen_candidate.get("expectation_gap")

        # Only run single-stock gate checks and committee deliberation if not multi-candidate or single candidate
        if ticker and ticker != "UNKNOWN" and (not is_multi_candidate or len(candidates) == 1):
            st = {**state, **updates}
            if chosen_candidate:
                if not st.get("market_context") and chosen_candidate.get("market_context"):
                    st["market_context"] = chosen_candidate["market_context"]
                if not st.get("sec_financials") and chosen_candidate.get("sec_financials"):
                    st["sec_financials"] = chosen_candidate["sec_financials"]
                if not st.get("consensus_snapshot") and chosen_candidate.get("consensus_snapshot"):
                    st["consensus_snapshot"] = chosen_candidate["consensus_snapshot"]
                if not st.get("expectation_gap") and chosen_candidate.get("expectation_gap"):
                    st["expectation_gap"] = chosen_candidate["expectation_gap"]
            updates["accounting_gate"] = evaluate_accounting_gate(st)
            updates["valuation_gate"] = evaluate_valuation_gate(st)
            updates["asymmetry_gate"] = evaluate_asymmetry_gate(st)

            if st.get("adversarial_report") and getattr(st["adversarial_report"], "numeric_kill_criteria", None):
                updates["thesis_breakers"] = list(st["adversarial_report"].numeric_kill_criteria)

            try:
                updates.update(run_investment_committee(st, model))
            except Exception as exc:
                logger.debug("Investment committee failed: %s", exc)

            if (
                updates["accounting_gate"].get("passed") is False
                or updates["valuation_gate"].get("passed") is False
                or updates["asymmetry_gate"].get("passed") is False
            ):
                if (state.get("research_intent") or {}).get("requested_position_decision"):
                    updates["status"] = "validation_required"

        return updates

    workflow = StateGraph(InvestigationState)
    for name, node in {
        "planner": planner_node,
        "executor": executor_node,
        "tools": ToolNode(tools),
        "ingest": ingest_node,
        "reflect": reflection_node,
        "diligence": diligence_node,
    }.items():
        workflow.add_node(name, node)

    # Entry point is structured planning
    workflow.set_entry_point("planner")
    workflow.add_edge("planner", "executor")

    # Dynamic execution loop with tools, ingest, and reflection
    workflow.add_conditional_edges(
        "executor",
        should_continue_executor,
        {"tools": "tools", "reflect": "reflect", "committee": "diligence"},
    )
    workflow.add_edge("tools", "ingest")
    workflow.add_edge("ingest", "executor")

    workflow.add_conditional_edges(
        "reflect",
        should_continue_reflection,
        {"executor": "executor", "committee": "diligence"},
    )
    workflow.add_edge("diligence", END)

    return workflow.compile(checkpointer=checkpointer)
