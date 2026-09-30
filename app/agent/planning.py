"""Structured deep-research planning and reflection schemas and orchestration.

Donor provenance: conceptual supervisor/planner and reflection patterns adapted from
LangChain Open Deep Research and GPT Researcher (skills/deep_research.py:259-378).
Local Pydantic schema validation and entity isolation are locally written.
"""
from __future__ import annotations

import json
import logging
import math
import re
from collections.abc import Mapping
from typing import Any, List, Literal, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Deterministic 4-Pillar Quantitative Factor Weights (Value, Quality, Momentum, Prudence/Size).
# Grounded in empirical asset pricing (Harvey, Liu, & Zhu 2016; AQR QMJ; Novy-Marx 2013).
SHORTLIST_WEIGHT_VALUE = 0.35
SHORTLIST_WEIGHT_QUALITY = 0.30
SHORTLIST_WEIGHT_MOMENTUM = 0.20
SHORTLIST_WEIGHT_PRUDENCE = 0.15
SHORTLIST_NEUTRAL_PERCENTILE = 0.5


def _percentile_ranks(values: list[Optional[float]]) -> list[float]:
    """Compute cross-sectional percentile ranks in [0, 1] for a value list.

    Missing (None) entries receive the neutral median percentile. Rank-based
    scoring is robust to outliers, standard practice for composite factor
    screens.

    Args:
        values: Numeric values; None marks a missing observation.

    Returns:
        Percentile rank per input position, ascending (higher value -> higher rank).
    """
    n = len(values)
    if n == 0:
        return []
    if n == 1:
        return [SHORTLIST_NEUTRAL_PERCENTILE]

    indexed = [(i, v) for i, v in enumerate(values) if v is not None]
    ranks = [SHORTLIST_NEUTRAL_PERCENTILE] * n
    if len(indexed) < 2:
        return ranks

    indexed.sort(key=lambda pair: pair[1])
    denom = len(indexed) - 1
    for pos, (i, _v) in enumerate(indexed):
        ranks[i] = pos / denom
    return ranks


def _parse_analyst_rating(rating: Any) -> tuple[Optional[float], Optional[int]]:
    """Parse a yfinance consensus rating string like '2.3 Buy (15)'.

    The yfinance scale is 1=strong buy ... 5=sell, so LOWER mean rating is
    MORE bullish conviction.

    Args:
        rating: Raw analyst rating string (or None).

    Returns:
        (mean_rating, analyst_count) with None for unparseable parts.
    """
    if not rating or not isinstance(rating, str):
        return None, None
    mean_match = re.search(r"^\s*(\d+(?:\.\d+)?)", rating)
    count_match = re.search(r"\((\d+)\)\s*$", rating)
    mean_val = float(mean_match.group(1)) if mean_match else None
    count_val = int(count_match.group(1)) if count_match else None
    return mean_val, count_val


def build_deterministic_shortlist(
    screen_rows: list[Mapping[str, Any]],
    top_n: int = 8,
) -> list[dict[str, Any]]:
    """Rank screener rows into a shortlist using an empirical 4-Pillar composite score.

    Pillars:
    1. Value (35%): Cross-sectional rank of inverse forward P/E (fallback trailing P/E).
    2. Quality (30%): Cross-sectional rank of inverse analyst rating + operating margin.
    3. Momentum (20%): 52-week price position (or day change) to guard against value traps.
    4. Prudence & Liquidity (15%): Log10 market cap prioritizing institutional liquidity.

    Hard gates drop rows with no market cap or no valuation multiple at all.

    Args:
        screen_rows: Screener output rows.
        top_n: Maximum shortlist size.

    Returns:
        Ranked shortlist rows (best first) with composite scores and pillar breakdowns.
    """
    gated: list[dict[str, Any]] = []
    for row in screen_rows:
        if not isinstance(row, Mapping):
            continue
        ticker = str(row.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        mcap = row.get("market_cap")
        fwd_pe = row.get("forward_pe")
        trail_pe = row.get("trailing_pe")
        # Hard gates: insufficient data to rank meaningfully.
        if mcap is None or (fwd_pe is None and trail_pe is None):
            continue
        gated.append({
            "ticker": ticker,
            "company": str(row.get("company") or ticker),
            "price": float(row.get("price")) if row.get("price") is not None else None,
            "market_cap": float(mcap),
            "forward_pe": float(fwd_pe) if fwd_pe is not None else None,
            "trailing_pe": float(trail_pe) if trail_pe is not None else None,
            "analyst_rating": row.get("analyst_rating"),
            "change_pct": float(row.get("change_pct")) if row.get("change_pct") is not None else None,
            "fifty_two_week_high": float(row.get("fifty_two_week_high")) if row.get("fifty_two_week_high") is not None else None,
            "fifty_two_week_low": float(row.get("fifty_two_week_low")) if row.get("fifty_two_week_low") is not None else None,
            "operating_margin": float(row.get("operating_margin")) if row.get("operating_margin") is not None else None,
        })

    if not gated:
        return []

    # 1. Value Pillar: cheaper P/E ranks higher
    value_basis = [(r["forward_pe"] if r["forward_pe"] is not None else r["trailing_pe"]) for r in gated]
    value_pcts = [1.0 - p for p in _percentile_ranks(value_basis)]

    # 2. Quality Pillar: lower consensus rating (bullish) + positive operating margin
    ratings = [_parse_analyst_rating(r["analyst_rating"])[0] for r in gated]
    conviction_pcts = [1.0 - p for p in _percentile_ranks(ratings)]
    margin_pcts = _percentile_ranks([r["operating_margin"] for r in gated])
    # Blend analyst conviction with reported operating margin when available
    quality_pcts = [
        round(0.70 * cp + 0.30 * mp, 4) if r["operating_margin"] is not None else cp
        for r, cp, mp in zip(gated, conviction_pcts, margin_pcts)
    ]

    # 3. Momentum Pillar (Value-Trap Circuit Breaker)
    # 52-week price position = (Price - Low) / (High - Low)
    momentum_basis: list[Optional[float]] = []
    for r in gated:
        price = r["price"]
        h52 = r["fifty_two_week_high"]
        l52 = r["fifty_two_week_low"]
        if price is not None and h52 is not None and l52 is not None and h52 > l52:
            momentum_basis.append((price - l52) / (h52 - l52))
        elif r["change_pct"] is not None:
            momentum_basis.append(r["change_pct"])
        else:
            momentum_basis.append(None)
    momentum_pcts = _percentile_ranks(momentum_basis)

    # 4. Prudence / Liquidity Pillar
    size_basis = [math.log10(max(r["market_cap"], 1.0)) for r in gated]
    size_pcts = _percentile_ranks(size_basis)

    scored: list[dict[str, Any]] = []
    for row, vp, qp, mp, sp in zip(gated, value_pcts, quality_pcts, momentum_pcts, size_pcts):
        mean_rating, analyst_count = _parse_analyst_rating(row["analyst_rating"])
        composite = (
            SHORTLIST_WEIGHT_VALUE * vp
            + SHORTLIST_WEIGHT_QUALITY * qp
            + SHORTLIST_WEIGHT_MOMENTUM * mp
            + SHORTLIST_WEIGHT_PRUDENCE * sp
        )
        scored.append({
            **row,
            "composite_score": round(composite, 4),
            "value_score": round(vp, 4),
            "quality_score": round(qp, 4),
            "momentum_score": round(mp, 4),
            "size_score": round(sp, 4),
            # Conviction score preserved for backward compatibility
            "conviction_score": round(qp, 4),
            "analyst_count": analyst_count,
        })

    scored.sort(key=lambda r: (-r["composite_score"], -(r["analyst_count"] or 0), r["ticker"]))
    return scored[:top_n]


class ResearchHypothesis(BaseModel):
    """A testable sub-question, claim, or hypothesis with an assigned evidence tier."""

    statement: str = Field(description="Actionable sub-question, hypothesis, or thesis to test.")
    evidence_tier: Literal["structured_quant", "primary_regulatory", "macro_series", "open_web"] = Field(
        default="open_web",
        description="The primary evidence quality tier required: 'structured_quant' for factor screening / ratios / DCF, 'primary_regulatory' for SEC 10-K/10-Q XBRL statements & footnote inspection, 'macro_series' for FRED economic rates/yields, or 'open_web' for industry whitepapers / news / PDFs.",
    )
    target_entity: Optional[str] = Field(
        default=None,
        description="Optional company ticker or macroeconomic entity associated with this hypothesis (e.g. 'NVDA', 'FEDFUNDS').",
    )


class CandidateAllocation(BaseModel):
    """Structured resource allocation assigning diligence depth per candidate."""

    ticker: str = Field(description="Candidate stock ticker symbol (e.g. 'NVDA').")
    priority: Literal["tier1_deep", "tier2_light"] = Field(
        default="tier1_deep",
        description="Diligence depth: 'tier1_deep' for full SEC XBRL de-cumulation, footnote parsing, and Reverse DCF; 'tier2_light' for fast baseline quantitative check.",
    )
    focus_mandate: str = Field(
        default="",
        description="Core catalyst, accounting risk, or growth hypothesis to investigate for this candidate.",
    )


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
        description="Explicit or high-opportunity candidate tickers or company names to investigate.",
    )
    candidate_allocations: List[CandidateAllocation] = Field(
        default_factory=list,
        description="Explicit priority and diligence tier per candidate entity to govern execution depth.",
    )
    primary_questions: List[str] = Field(
        default_factory=list,
        description="3 to 5 targeted, answerable sub-questions that must be investigated.",
    )
    hypotheses: List[ResearchHypothesis] = Field(
        default_factory=list,
        description="Structured sub-hypotheses with target evidence tiers for dynamic DAG execution.",
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


class PlannerScoutQuery(BaseModel):
    """Targeted search query targeting a specific discovery tool."""

    tool_name: Literal["search_web", "search_articles", "search_social", "screen_stocks"] = Field(
        default="search_web",
        description="The discovery tool to invoke: 'screen_stocks' for quantitative factor/preset screening, 'search_web' for general web/catalysts, 'search_articles' for news/earnings/regulatory articles, or 'search_social' for retail/sentiment trends.",
    )
    query: str = Field(
        default="",
        description="Concise, keyword-optimized search query (NOT conversational phrases or questions). E.g. 'top enterprise tech free cash flow growth 2026'.",
    )
    sector: Optional[str] = Field(
        default=None,
        description="Optional GICS sector filter when tool_name is 'screen_stocks' (e.g. 'Technology', 'Healthcare', 'Financial Services').",
    )
    preset: Optional[str] = Field(
        default=None,
        description="Optional preset when tool_name is 'screen_stocks' (e.g. 'growth_technology_stocks', 'undervalued_large_caps', 'most_actives').",
    )
    limit: int = Field(
        default=10,
        ge=1,
        le=20,
        description="Maximum rows/results to request. Use 20 for 'screen_stocks' (widest net) and up to 10 for web/article/social queries.",
    )


class PlannerScoutAssessment(BaseModel):
    """Initial assessment of the user prompt to determine if live preliminary discovery is required."""

    needs_scouting: bool = Field(
        default=False,
        description="True if the request is an open-ended screening or thematic inquiry where candidate tickers or recent catalysts need discovery.",
    )
    scout_queries: List[PlannerScoutQuery] = Field(
        default_factory=list,
        description="Up to 4 targeted discovery queries (prefer 1-2 screen_stocks presets to widen the net plus 1-2 web/article/social queries). Empty if explicit companies or tickers were already provided.",
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
        if schema is ResearchPlanSchema:
            return schema(brief=str(getattr(last_msg, "content", "")))
        if schema is PlannerScoutAssessment:
            return schema(needs_scouting=False, scout_queries=[])
        return schema(is_research_complete=True)


def assess_scout_need(
    model: Any,
    query: str,
    ticker: Optional[str] = None,
    company: Optional[str] = None,
) -> PlannerScoutAssessment:
    """Assess whether a research prompt requires preliminary discovery scouting and generate targeted queries.

    Args:
        model: Language model runtime.
        query: Free-form user research prompt.
        ticker: Optional explicit single ticker if already provided.
        company: Optional explicit company name if already provided.

    Returns:
        Validated PlannerScoutAssessment instance.
    """
    # Fast path: if the user already provided an explicit ticker or company, scouting is unnecessary
    if ticker or company:
        return PlannerScoutAssessment(needs_scouting=False, scout_queries=[])

    if not hasattr(model, "with_structured_output"):
        # Fallback for models without structured output: assume scouting is needed only if prompt is non-empty
        return PlannerScoutAssessment(
            needs_scouting=bool(str(query).strip()),
            scout_queries=[PlannerScoutQuery(tool_name="search_web", query=str(query)[:120])] if str(query).strip() else [],
        )

    system_prompt = SystemMessage(
        content=(
            "You are a Senior Investment Research Architect.\n"
            "Evaluate the user's research request to determine whether preliminary discovery scouting is needed.\n"
            "Rules:\n"
            "1. If the user names specific target companies/tickers (e.g., 'Analyze AAPL' or 'Compare MSFT and GOOGL'), scouting is NOT needed (needs_scouting=False).\n"
            "2. If the user request is open-ended, thematic, or asks for screening/recommendations (e.g., 'find best 2 stocks in tech', 'top defense stocks 2026', 'trending AI hardware plays'), set needs_scouting=True.\n"
            "3. When scouting is needed, WIDEN FIRST: formulate 1 to 2 'screen_stocks' queries (preset and/or sector filters matching the theme, limit=20) plus 1 to 2 web/article/social queries for thematic names the screener cannot express. Use concise, keyword-optimized queries (NOT conversational sentences).\n"
            "4. Choose the best tool for each query:\n"
            "   - 'screen_stocks': for quantitative screening by sector or preset (e.g. sector='Technology', or preset='growth_technology_stocks' / 'undervalued_large_caps'). Prioritize this when looking for stocks in a sector or category.\n"
            "   - 'search_web': for general industry rankings, analyst commentary, or sector leaders.\n"
            "   - 'search_articles': for recent news, earnings announcements, M&A, or regulatory catalysts.\n"
            "   - 'search_social': for retail buzz, meme stocks, or sentiment spikes on Reddit/ApeWisdom/StockTwits.\n"
            "5. Set limit=20 for screen_stocks queries and limit<=10 for web/article/social queries.\n"
            "6. Maximum 4 queries total."
        )
    )
    user_text = f"Research Request: {query}"
    messages = [system_prompt, HumanMessage(content=user_text)]
    try:
        result = _invoke_structured(model, messages, PlannerScoutAssessment)
        if isinstance(result, PlannerScoutAssessment):
            return result
        if isinstance(result, dict):
            return PlannerScoutAssessment.model_validate(result)
    except Exception as exc:
        logger.warning("assess_scout_need failed (%s); proceeding without scouting", exc)

    return PlannerScoutAssessment(needs_scouting=False, scout_queries=[])


def generate_research_plan(
    model: Any,
    query: str,
    ticker: Optional[str] = None,
    company: Optional[str] = None,
    scout_context: Optional[str] = None,
    as_of_date: Optional[str] = None,
    max_tool_calls: Optional[int] = None,
) -> ResearchPlanSchema:
    """Generate a structured research plan from user prompt using LLM structured output.

    Args:
        model: Language model runtime.
        query: Free-form user research prompt.
        ticker: Optional explicit single ticker if provided by caller.
        company: Optional explicit company name if provided by caller.
        scout_context: Optional preliminary web/news snippets gathered prior to planning.
        as_of_date: Optional PIT cutoff date for backtest discipline.
        max_tool_calls: Optional execution tool budget ceiling.

    Returns:
        Validated ResearchPlanSchema instance.
    """
    system_prompt = SystemMessage(content=(
        "You are an expert financial research planner and investigation architect.\n"
        "Analyze the user's research request and construct a rigorous, structured Deep Research Plan.\n"
        "Guidelines:\n"
        "1. Identify whether this is a multi-candidate ranking/screening, a single-company deep diligence, or a general thematic investigation.\n"
        "2. If the user asks for a specific count (e.g. '5 best tech stocks', 'top 10 AI companies', 'compare 3 peers'), set ranking_count to that integer.\n"
        "3. Identify explicit or promising candidate entities (tickers/names) to investigate. If preliminary scout intelligence is provided, use it to ground exact real-world tickers and entities.\n"
        "4. Assign candidate_allocations to govern execution depth: prioritize high-conviction ideas into 'tier1_deep' (full SEC XBRL, footnote parsing, and Reverse DCF) and secondary ideas into 'tier2_light' (baseline quant/quote checks).\n"
        "5. Formulate 3 to 5 targeted, high-signal hypotheses/questions with appropriate evidence_tier assignments:\n"
        "   - 'structured_quant' for factor screening, market quotes, valuation multiples, and Reverse DCF.\n"
        "   - 'primary_regulatory' for audited SEC 10-K/10-Q XBRL statements, footnote inspection, and Form 4 insider trades.\n"
        "   - 'macro_series' for interest rates, inflation, treasury yields, or currency liquidity via FRED.\n"
        "   - 'open_web' for broad industry trends, executive commentary, supply chain news, or whitepaper PDFs.\n"
        "6. Set requires_candidate_workspaces to True whenever multiple candidate companies are being researched or compared."
    ))

    user_text = f"Research Request: {query}"
    if as_of_date:
        user_text += f"\nPoint-In-Time Research As-Of Date: {as_of_date}"
    if ticker:
        user_text += f"\nExplicit Ticker: {ticker}"
    if company:
        user_text += f"\nExplicit Company: {company}"
    if max_tool_calls is not None:
        user_text += f"\nAvailable Execution Tool Budget: {max_tool_calls} total tool calls. Ensure your planned investigation and candidate count are achievable within this budget limit."
    if scout_context and scout_context.strip():
        user_text += f"\n\nPreliminary Scout Intelligence (Live Discovery):\n{scout_context.strip()}"

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
            sec_corpora = c.get("sec_corpora") or []
            sec_investigations = c.get("sec_investigations") or []
            dossier = c.get("diligence_dossier") or {}
            candidate_summary[cid] = {
                "ticker": c.get("ticker"),
                "company": c.get("company"),
                "has_market_data": bool(c.get("market_context")),
                "sec_financials_status": fin_status,
                "sec_filings_count": len(c.get("sec_filings") or []),
                "sec_corpora_count": len(sec_corpora),
                "sec_investigations_count": len(sec_investigations),
                "has_sec_evidence": bool(sec_corpora or sec_investigations or c.get("evidence")),
                "diligence_status": dossier.get("status") if isinstance(dossier, dict) else "missing",
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
        "2. Treat has_sec_evidence=True, sec_corpora_count>0, or sec_investigations_count>0 as verified SEC coverage even when sec_filings_count is zero; do not request another filing pull merely because the discovery list was not routed into state.\n"
        "3. If a foreign issuer (e.g. Form 20-F/6-K filers) lacks standard US-GAAP XBRL facts, note that and verify whether market fundamentals or 20-F filing searches were used.\n"
        "4. Is the cross-candidate comparison matrix populated?\n"
        "5. If significant gaps exist, specify them in evidence_gaps and set is_research_complete to False.\n"
        "6. If all essential questions have sufficient cited evidence, set is_research_complete to True."
    ))

    user_text = f"Current Research Evidence State:\n{json.dumps(state_summary, indent=2)}"
    messages = [system_prompt, HumanMessage(content=user_text)]
    return _invoke_structured(model, messages, ResearchReflectionSchema)
