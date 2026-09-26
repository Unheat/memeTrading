"""Air-gapped Bull Case Advocate node for asymmetric upside discovery.

Donor provenance: adapted from reference/investment-research/contracts/bull.yaml:1-24
and reference/investment-research/schemas/bull-case.schema.json.
(Builds the strongest honest case that the market is mispricing this business to the upside).
Runs under complete context isolation from bearish red team drafts to eliminate premature compromise.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from app.agent.contracts import BullCase, parse_llm_json_block
from app.agent.state import InvestigationState

logger = logging.getLogger(__name__)

# One structured retry with validation feedback before flagging the report degraded
# (audit 2026-09-26, Fix 6).
BULL_MAX_ATTEMPTS = 2

BULL_SYSTEM_PROMPT = """You are the Senior Long Strategist and Head of the Bull Case unit at an institutional hedge fund.
Your sole mission is to build the strongest, numbers-backed case that the market is materially mispricing this asset to the upside.

You do not engage in wishful thinking or generic cheerleading. You hunt for structural inflections:
operating leverage, pricing power, unmodeled TAM expansion, accelerating gross margin trajectory, customer backlog durability, supply-chain choke points, and upward consensus revisions.

CRITICAL BULL STANDARDS:
1. Three Minimum Falsifiable Catalysts: Formulate at least 3 distinct, observable catalysts with specific timelines (e.g. "Catalyst 1: Next-gen high-margin product ramp drives 350 bps gross margin expansion over next 2 quarters", "Catalyst 2: Hyperscaler enterprise backlog secures 100% capacity pre-commitments").
2. Operating Leverage Drivers: Identify explicit structural drivers where revenue growth outpaces fixed fab/operating costs, driving outsized EPS acceleration.
3. Realistic Bull Target Price: Formulate a disciplined upside price target based on historical expansion multiples and fundamental earnings power.
4. What Would Change My Mind: Define explicit conditions where you would abandon this bull thesis.

Return strictly valid JSON matching this exact structure:
{
  "catalysts": [
    "Catalyst 1...",
    "Catalyst 2...",
    "Catalyst 3..."
  ],
  "operating_leverage_drivers": [
    "Driver 1...",
    "Driver 2..."
  ],
  "bull_target_price": 120.0,
  "bull_thesis_summary": "Core structural upside argument...",
  "invalidation_conditions": [
    "Condition 1..."
  ]
}
"""


class BullReport(BullCase):
    """Structured report produced by the air-gapped Bull Case Advocate."""
    pass


def run_bull_advocate(state: InvestigationState, model: Any) -> dict[str, Any]:
    """Execute the air-gapped Bull Case analysis against accumulated facts.

    :param state: Current investigation state holding facts and trigger.
    :param model: Language model double or LLM instance.
    :returns: State updates with bull report.
    """
    ticker = state.get("ticker") or "UNKNOWN"
    evidence = state.get("evidence", [])
    market = state.get("market_context") or {}
    consensus = state.get("consensus_snapshot") or {}
    trigger = state.get("trigger", {})

    facts_payload = json.dumps(
        {
            "ticker": ticker,
            "theme": trigger.get("theme"),
            "investigation_query": trigger.get("query"),
            "market_context": {
                "price": (market.get("quote") or {}).get("price"),
                "returns": market.get("returns"),
                "volume_ratio_20d": market.get("volume_ratio_20d"),
                "fundamentals": market.get("fundamentals"),
            },
            "consensus_snapshot": {
                "mean_target": (consensus.get("price_targets") or {}).get("mean"),
                "high_target": (consensus.get("price_targets") or {}).get("high"),
                "ratings": consensus.get("ratings"),
                "eps_estimates": consensus.get("eps_estimates"),
                "revenue_estimates": consensus.get("revenue_estimates"),
            },
            "verified_evidence_quotes": [e.get("quote") for e in evidence if e.get("quote")],
        },
        indent=2,
        default=str,
    )

    human_prompt = f"""Target Company: ${ticker}

Audited Fundamental Facts & Consensus Data:
```json
{facts_payload}
```

Construct the institutional Bull Case. Identify the core upside mispricing, at least 3 distinct catalysts, operating leverage drivers, and a target price. Return strictly the required JSON."""

    # Fix 6 (audit 2026-09-26): the committee's asymmetry anchors are symmetric only if
    # the bull side supplies a numeric target. One structured retry is allowed with the
    # validation error fed back before the report is flagged degraded.
    validation_feedback = (
        "Your previous response was missing a valid numeric 'bull_target_price'. "
        "Return the same JSON structure with a concrete numeric price target above the current market price."
    )
    data: dict[str, Any] | None = None
    target_price: float | None = None
    degradation_reasons: list[str] = []
    for attempt in range(BULL_MAX_ATTEMPTS):
        messages = [SystemMessage(content=BULL_SYSTEM_PROMPT), HumanMessage(content=human_prompt)]
        if attempt > 0:
            messages.append(HumanMessage(content=validation_feedback))
        try:
            response = model.invoke(messages)
            data = parse_llm_json_block(getattr(response, "content", ""))
        except Exception as exc:
            logger.warning("Bull Advocate invocation failed for %s (attempt %s): %s", ticker, attempt + 1, exc)
            data = None
        if data is not None:
            raw_price = data.get("bull_target_price")
            try:
                target_price = float(raw_price) if raw_price is not None else None
            except (ValueError, TypeError):
                target_price = None
            if target_price is not None and target_price > 0:
                break
            degradation_reasons.append(f"attempt {attempt + 1}: bull_target_price missing or non-positive")
            target_price = None

    if data is None:
        report = BullReport(
            ticker=ticker,
            catalysts=(),
            operating_leverage_drivers=(),
            bull_target_price=None,
            bull_thesis_summary="Unavailable — bull analysis did not return valid JSON.",
            invalidation_conditions=(),
            status="unavailable",
            degradation_reasons=tuple(degradation_reasons) or ("model returned unparseable JSON after retry",),
        )
    elif target_price is None:
        report = BullReport(
            ticker=ticker,
            catalysts=tuple(str(c) for c in (data.get("catalysts") or []) if str(c).strip()),
            operating_leverage_drivers=tuple(str(d) for d in (data.get("operating_leverage_drivers") or []) if str(d).strip()),
            bull_target_price=None,
            bull_thesis_summary=data.get("bull_thesis_summary") or "Bullish mispricing identified.",
            invalidation_conditions=tuple(str(c) for c in (data.get("invalidation_conditions") or []) if str(c).strip()),
            status="degraded",
            degradation_reasons=tuple(degradation_reasons),
        )
    else:
        report = BullReport(
            ticker=ticker,
            catalysts=tuple(str(c) for c in (data.get("catalysts") or []) if str(c).strip()),
            operating_leverage_drivers=tuple(str(d) for d in (data.get("operating_leverage_drivers") or []) if str(d).strip()),
            bull_target_price=target_price,
            bull_thesis_summary=data.get("bull_thesis_summary") or "Bullish mispricing identified.",
            invalidation_conditions=tuple(str(c) for c in (data.get("invalidation_conditions") or []) if str(c).strip()),
            status="available",
            degradation_reasons=(),
        )

    return {"bull_report": report}
