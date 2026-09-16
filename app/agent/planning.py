"""Structured deep-research planning and reflection schemas and orchestration.

Donor provenance: conceptual supervisor/planner and reflection patterns adapted from
LangChain Open Deep Research and GPT Researcher (skills/deep_research.py:259-378).
Local Pydantic schema validation and entity isolation are locally written.
"""
from __future__ import annotations

import json
import logging
from typing import Any, List, Literal, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ResearchPlanSchema(BaseModel):
    """Structured deep research plan generated from the user's free-form prompt."""

    brief: str = Field(description="One-sentence executive summary of the research mandate.")
    research_type: Literal["multi_candidate_ranking", "single_diligence", "general_deep_dive"] = Field(
        default="general_deep_dive",
        description="The structural type of research required.",
    )
    ranking_count: Optional[int] = Field(
        default=None,
        description="Explicit number of candidates requested to rank (e.g. 5 for '5 best tech stocks'). None if no ranking count specified.",
    )
    candidate_entities: List[str] = Field(
        default_factory=list,
        description="Explicit or high-opportunity candidate tickers or company names to investigate (e.g. ['MSFT', 'NVDA', 'GOOGL', 'AVGO', 'TSM']).",
    )
    primary_questions: List[str] = Field(
        default_factory=list,
        description="3 to 5 targeted, answerable sub-questions that must be investigated.",
    )
    requires_candidate_workspaces: bool = Field(
        default=False,
        description="True if multiple entities are being analyzed and require separate candidate workspaces.",
    )
    requested_position_decision: bool = Field(
        default=False,
        description="True only if the user explicitly requested a specific capital allocation or position decision on a single company.",
    )


class ResearchReflectionSchema(BaseModel):
    """Structured gap analysis evaluating current evidence against the research plan."""

    is_research_complete: bool = Field(
        description="True if the gathered evidence and comparisons adequately address the research plan.",
    )
    evidence_gaps: List[str] = Field(
        default_factory=list,
        description="Specific missing metrics, unread SEC filings, unverified claims, or provider degradations.",
    )
    suggested_follow_up_tools: List[str] = Field(
        default_factory=list,
        description="Suggested specific tool calls or search queries to execute in the next reflection round.",
    )


def _invoke_structured(model: Any, messages: list[Any], schema: type[BaseModel]) -> BaseModel:
    """Invoke model with structured output, supporting UniversalChatModel, LangChain, and test doubles."""
    if hasattr(model, "with_structured_output"):
        try:
            runnable = model.with_structured_output(schema)
            result = runnable.invoke(messages)
            if isinstance(result, schema):
                return result
            if isinstance(result, dict):
                return schema.model_validate(result)
        except Exception as exc:
            logger.debug("with_structured_output failed (%s); falling back to direct JSON prompt", exc)

    # Fallback for models or test doubles: prompt with JSON schema instruction
    schema_json = schema.model_json_schema()
    instruction = (
        f"\nYou MUST respond strictly in valid JSON conforming to this JSON schema:\n"
        f"{json.dumps(schema_json, indent=2)}\n"
        f"Do not include any commentary, prose, or markdown fences outside the JSON object."
    )
    augmented_messages = list(messages)
    last_msg = augmented_messages[-1]
    augmented_messages[-1] = HumanMessage(content=str(getattr(last_msg, "content", "")) + instruction)

    response = model.invoke(augmented_messages)
    raw_content = str(getattr(response, "content", "")).strip()

    # Clean potential markdown fences
    if raw_content.startswith("```json"):
        raw_content = raw_content[7:]
    elif raw_content.startswith("```"):
        raw_content = raw_content[3:]
    if raw_content.endswith("```"):
        raw_content = raw_content[:-3]
    raw_content = raw_content.strip()

    try:
        data = json.loads(raw_content)
        return schema.model_validate(data)
    except Exception as exc:
        logger.warning("Failed to parse structured output from model: %s. Raw: %s", exc, raw_content[:200])
        # Return fallback default instance if model failed
        return schema(brief=str(getattr(last_msg, "content", ""))) if schema is ResearchPlanSchema else schema(is_research_complete=True)


def generate_research_plan(
    model: Any,
    query: str,
    ticker: Optional[str] = None,
    company: Optional[str] = None,
) -> ResearchPlanSchema:
    """Generate a structured research plan from user prompt using LLM structured output.

    Args:
        model: Language model runtime.
        query: Free-form user research prompt.
        ticker: Optional explicit single ticker if provided by caller.
        company: Optional explicit company name if provided by caller.

    Returns:
        Validated ResearchPlanSchema instance.
    """
    system_prompt = SystemMessage(content=(
        "You are an expert financial research planner and investigation architect.\n"
        "Analyze the user's research request and construct a rigorous, structured Deep Research Plan.\n"
        "Guidelines:\n"
        "1. Identify whether this is a multi-candidate ranking/screening, a single-company deep diligence, or a general thematic investigation.\n"
        "2. If the user asks for a specific count (e.g. '5 best tech stocks', 'top 10 AI companies', 'compare 3 peers'), set ranking_count to that integer.\n"
        "3. Identify explicit or promising candidate entities (tickers/names) to investigate.\n"
        "4. Formulate 3 to 5 targeted, high-signal questions focusing on valuation, real financial performance (SEC/XBRL), operational durability, and market setup.\n"
        "5. Set requires_candidate_workspaces to True whenever multiple candidate companies are being researched or compared."
    ))

    user_text = f"Research Request: {query}"
    if ticker:
        user_text += f"\nExplicit Ticker: {ticker}"
    if company:
        user_text += f"\nExplicit Company: {company}"

    messages = [system_prompt, HumanMessage(content=user_text)]
    return _invoke_structured(model, messages, ResearchPlanSchema)


def reflect_on_research_gaps(
    model: Any,
    plan: ResearchPlanSchema,
    candidates: dict[str, Any],
    comparisons: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    searches_performed: list[dict[str, Any]],
) -> ResearchReflectionSchema:
    """Evaluate current research progress against the plan and propose targeted follow-ups.

    Args:
        model: Language model runtime.
        plan: The active ResearchPlanSchema.
        candidates: Candidate workspaces dictionary.
        comparisons: Candidate comparison cards.
        sources: Discovered source records.
        searches_performed: Audit log of tool receipts.

    Returns:
        Validated ResearchReflectionSchema instance.
    """
    candidate_summary = {}
    for cid, c in candidates.items():
        if isinstance(c, dict):
            sec_fin = c.get("sec_financials") or {}
            fin_status = sec_fin.get("status") if isinstance(sec_fin, dict) else "missing"
            candidate_summary[cid] = {
                "ticker": c.get("ticker"),
                "company": c.get("company"),
                "has_market_data": bool(c.get("market_context")),
                "sec_financials_status": fin_status,
                "sec_filings_count": len(c.get("sec_filings") or []),
            }

    state_summary = {
        "plan_brief": plan.brief,
        "research_type": plan.research_type,
        "ranking_count": plan.ranking_count,
        "candidates": candidate_summary,
        "candidate_comparisons_count": len(comparisons),
        "sources_count": len(sources),
        "tool_receipts_count": len(searches_performed),
        "recent_errors": [
            r.get("error") for r in searches_performed if r.get("status") == "error" and r.get("error")
        ][-5:],
    }

    system_prompt = SystemMessage(content=(
        "You are an investigative research lead conducting evidence gap reflection.\n"
        "Review the current state of gathered evidence against the original research plan.\n"
        "Check:\n"
        "1. Did we gather market data and financial evidence for all requested candidates?\n"
        "2. If a foreign issuer (e.g. Form 20-F/6-K filers like TSM) lacks standard US-GAAP XBRL facts, note that and verify whether market fundamentals or 20-F filing searches were used.\n"
        "3. Is the cross-candidate comparison matrix populated?\n"
        "4. If significant gaps exist, specify them in evidence_gaps and set is_research_complete to False.\n"
        "5. If all essential questions have sufficient cited evidence, set is_research_complete to True."
    ))

    user_text = f"Current Research Evidence State:\n{json.dumps(state_summary, indent=2)}"
    messages = [system_prompt, HumanMessage(content=user_text)]
    return _invoke_structured(model, messages, ResearchReflectionSchema)
