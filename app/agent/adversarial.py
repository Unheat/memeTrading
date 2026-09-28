"""Air-gapped adversarial short-seller red team node.

Donor provenance: adapted from reference/investment-research/prompts/bear-adversarial.prompt.md:1-35
(Hostile short-seller mindset, minimum 4 falsifiable objections, 2 numeric kill criteria).
Runs under complete context isolation from bullish narrative drafts to eliminate confirmation bias.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any
from langchain_core.messages import HumanMessage, SystemMessage
from app.agent.contracts import BearCase, parse_llm_json_block
from app.agent.state import InvestigationState

logger = logging.getLogger(__name__)

ADVERSARIAL_SYSTEM_PROMPT = """# System Prompt: Adversarial Short-Seller & Red Team Stress Tester (`bear-adversarial`)

You are an activist short-seller and head of the Red Team Stress Testing unit at an elite institutional hedge fund. Your mission is to actively destroy the consensus bull case.

---

## Adversarial Standards

1. **Hostile Skepticism**:
   You do not look for reasons why the stock might do well; the Bull agent does that. You look for structural flaws, technological obsolescence, competitive erosion, margin collapse, channel stuffing, customer churn, and multiple derating.
2. **Four Minimum Falsifiable Objections**:
   You must formulate at least 4 distinct, falsifiable objections with explicit mechanisms. Generic risks like "macro could slow" are rejected as defects.
   - Example mechanism: *"Internal ASIC ramp across key customers will commoditize merchant chip demand by Year 3, compressing gross margins from 75% down to 58%."*
   - Example mechanism: *"Regulatory approval of two major well-funded rival platforms will introduce customer procurement price bidding, ending the incumbent's 40x multiple premium."*
3. **Two Numeric Kill Criteria (Invalidation Triggers)**:
   You must provide at least 2 explicit numerical thresholds where the thesis is provably broken:
   - Example: *"Kill Trigger 1: Consolidated Free Cash Flow margin drops below 18.0% for 2 consecutive quarters."*
   - Example: *"Kill Trigger 2: Cloud segment Net Revenue Retention (NRR) slows below 110%."*
4. **Empirically Grounded Downside Bear Floor (`bear_floor_price`)**:
   - The Bear Floor must be an empirically grounded downside anchor based on financial reality, NOT an arbitrary catastrophic crash.
   - Anchor the floor to institutional valuation supports provided in the evidence:
     * Street Consensus Low Target: The lowest price target among covering Wall Street analysts.
     * Trough Valuation Multiple: Trough P/E (e.g. 10x-15x on normalized earnings) or low-case DCF fair value.
     * Balance Sheet Support: Tangible book value per share or net cash per share.
   - For profitable, cash-generative market leaders with fortress balance sheets and expanding free cash flows, the bear floor represents a realistic cyclical drawdown (typically 10%–25% below market price, or bounded by the Street Low target), NOT an unevidenced bankruptcy scenario unless fraud or insolvency is proven.
   - For speculative, unprofitable, or debt-heavy turnarounds, a deeper downside floor (e.g. tangible asset liquidation or restructuring floor) is appropriate.
5. **Isolation Barrier**:
   You run in strict isolation from the Bull agent. You do not see their draft. You cannot soften or negotiate your objections.

---

## Output Standard
Return strictly valid JSON matching this exact structure:
{
  "falsifiable_objections": [
    "Mechanism 1...",
    "Mechanism 2...",
    "Mechanism 3...",
    "Mechanism 4..."
  ],
  "numeric_kill_criteria": [
    "Kill Trigger 1...",
    "Kill Trigger 2..."
  ],
  "bear_floor_price": 75.0,
  "bear_thesis_summary": "Core structural failure argument..."
}
"""



class AdversarialReport(BearCase):
    """Structured report produced by the air-gapped short-seller red team."""
    pass


def run_adversarial_red_team(state: InvestigationState, model: Any) -> dict[str, Any]:
    """Execute the air-gapped short-seller attack against accumulated facts.

    :param state: Current investigation state holding facts and trigger.
    :param model: Language model double or LLM instance.
    :returns: State updates with adversarial report and thesis breakers.
    """
    ticker = state.get("ticker") or "UNKNOWN"
    evidence = state.get("evidence", [])
    contradictions = state.get("contradictions", [])
    market = state.get("market_context") or {}
    consensus = state.get("consensus_snapshot") or {}
    quant = state.get("quant_report") or {}
    quant_val = quant.get("valuation") or {}

    facts_payload = json.dumps(
        {
            "ticker": ticker,
            "company": state.get("company"),
            "trigger": state.get("trigger"),
            "root_claims": state.get("root_claims"),
            "verified_evidence": evidence,
            "contradictions": contradictions,
            "market_context": market,
            "consensus_snapshot": consensus,
            "quant_valuation_low_case": ((quant_val.get("fair_value_range") or {}).get("low") or (quant_val.get("cases", {}).get("low", {}) or {}).get("fair_value_per_share")),
        },
        indent=2,
    )

    human_prompt = f"""Conduct a hostile short-seller red team attack on ${ticker}.

Verified Evidence and Facts gathered:
```json
{facts_payload}
```

Identify the 4 structural flaws, 2 numeric kill triggers, and realistic, empirically grounded bear floor price.
"""

    response = model.invoke([
        SystemMessage(content=ADVERSARIAL_SYSTEM_PROMPT),
        HumanMessage(content=human_prompt),
    ])

    try:
        # Field-level parsing (audit 2026-09-26, Fix 7): one malformed field degrades
        # the report instead of discarding it wholesale.
        data = parse_llm_json_block(getattr(response, "content", ""))

        def _extract_text(item: Any) -> str:
            if isinstance(item, dict):
                return str(item.get("mechanism") or item.get("objection") or item.get("thesis") or item.get("description") or item.get("criterion") or item.get("metric") or item).strip()
            return str(item).strip()

        objections = tuple(_extract_text(x) for x in (data.get("falsifiable_objections") or []) if _extract_text(x))
        kill_criteria = tuple(_extract_text(x) for x in (data.get("numeric_kill_criteria") or []) if _extract_text(x))
        bear_floor = None
        raw_floor = data.get("bear_floor_price")
        try:
            bear_floor = float(raw_floor) if raw_floor is not None else None
        except (ValueError, TypeError):
            bear_floor = None
        summary = str(data.get("bear_thesis_summary") or "Adversarial short-seller attack completed.")

        degradation_reasons = []
        if bear_floor is None:
            degradation_reasons.append("bear_floor_price missing or non-numeric")
        if not kill_criteria:
            degradation_reasons.append("numeric_kill_criteria missing or empty")
        status = "degraded" if degradation_reasons else "available"

        report = AdversarialReport(
            ticker=ticker,
            falsifiable_objections=objections,
            numeric_kill_criteria=kill_criteria,
            bear_floor_price=bear_floor,
            bear_thesis_summary=summary,
            status=status,
            degradation_reasons=tuple(degradation_reasons),
        )
        return {
            "thesis_breakers": list(kill_criteria),
            "adversarial_report": report,
        }
    except Exception as exc:
        logger.warning("Adversarial red team parsing failed for %s: %s", ticker, exc)
        report = AdversarialReport(
            ticker=ticker,
            falsifiable_objections=(),
            numeric_kill_criteria=(),
            bear_floor_price=None,
            bear_thesis_summary="Unavailable — adversarial analysis did not return valid JSON.",
            status="unavailable",
            degradation_reasons=(f"model returned unparseable JSON: {exc}",),
        )
        return {"thesis_breakers": [], "adversarial_report": report}
