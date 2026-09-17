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
from app.agent.contracts import BearCase
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
   - Example mechanism: *"Hyperscaler internal ASIC ramp (Google TPU, Amazon Trainium) will commoditize merchant GPU demand by Year 3, compressing gross margins from 75% down to 58%."*
   - Example mechanism: *"FDA approval of Medtronic Hugo and J&J Ottava in 2026 will introduce hospital procurement price bidding, ending Intuitive Surgical's 42x multiple premium."*
3. **Two Numeric Kill Criteria (Invalidation Triggers)**:
   You must provide at least 2 explicit numerical thresholds where the thesis is provably broken:
   - Example: *"Kill Trigger 1: Consolidated Free Cash Flow margin drops below 18.0% for 2 consecutive quarters."*
   - Example: *"Kill Trigger 2: Cloud segment Net Revenue Retention (NRR) slows below 110%."*
4. **Isolation Barrier**:
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
        },
        indent=2,
    )

    human_prompt = f"""Conduct a hostile short-seller red team attack on ${ticker}.

Verified Evidence and Facts gathered:
```json
{facts_payload}
```

Identify the 4 structural flaws, 2 numeric kill triggers, and realistic bear floor price.
"""

    response = model.invoke([
        SystemMessage(content=ADVERSARIAL_SYSTEM_PROMPT),
        HumanMessage(content=human_prompt),
    ])

    raw_content = getattr(response, "content", "")
    try:
        # Extract JSON block if wrapped in markdown code fence
        clean_json = raw_content
        if "```json" in clean_json:
            clean_json = clean_json.split("```json")[1].split("```")[0].strip()
        elif "```" in clean_json:
            clean_json = clean_json.split("```")[1].split("```")[0].strip()
        data = json.loads(clean_json)

        objections = tuple(str(x) for x in data.get("falsifiable_objections", []))
        kill_criteria = tuple(str(x) for x in data.get("numeric_kill_criteria", []))
        bear_floor = float(data["bear_floor_price"]) if data.get("bear_floor_price") is not None else None
        summary = str(data.get("bear_thesis_summary", "Adversarial short-seller attack completed."))

        report = AdversarialReport(
            ticker=ticker,
            falsifiable_objections=objections,
            numeric_kill_criteria=kill_criteria,
            bear_floor_price=bear_floor,
            bear_thesis_summary=summary,
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
        )
        return {"thesis_breakers": [], "adversarial_report": report}
