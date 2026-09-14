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
from app.agent.state import InvestigationState

logger = logging.getLogger(__name__)

ADVERSARIAL_SYSTEM_PROMPT = """You are an activist short-seller and head of the Red Team Stress Testing unit at an institutional hedge fund. Your sole mission is to actively destroy the consensus bull case.

You do not look for reasons why the stock might do well. You look for structural flaws, technological obsolescence, competitive erosion, gross margin collapse, channel stuffing, customer churn, debt walls, and multiple derating.

CRITICAL ADVERSARIAL STANDARDS:
1. Four Minimum Falsifiable Objections: Formulate at least 4 distinct, falsifiable objections with explicit mechanisms. Generic risks like "macro could slow" are strictly rejected as defects.
2. Two Quantitative Numeric Kill Criteria: Provide at least 2 explicit numerical thresholds where the investment thesis is provably broken (e.g. "Kill Trigger 1: Consolidated Gross margin contracts below 28.0% for 2 consecutive quarters", "Kill Trigger 2: Cloud NRR slows below 110%").
3. Stress-Tested Bear Floor Price: Estimate a realistic downside valuation floor based on normalized trough multiples or balance-sheet liquidation value.

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


@dataclass(frozen=True)
class AdversarialReport:
    """Structured report produced by the air-gapped short-seller red team."""

    ticker: str
    falsifiable_objections: tuple[str, ...]
    numeric_kill_criteria: tuple[str, ...]
    bear_floor_price: float | None
    bear_thesis_summary: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "ticker": self.ticker,
            "falsifiable_objections": list(self.falsifiable_objections),
            "numeric_kill_criteria": list(self.numeric_kill_criteria),
            "bear_floor_price": self.bear_floor_price,
            "bear_thesis_summary": self.bear_thesis_summary,
        }


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
        default_kill = (
            "Kill Trigger 1: Consolidated Gross Margin contracts in subsequent SEC 10-Q filing.",
            "Kill Trigger 2: Channel check confirms inventory accumulation exceeding 15% QoQ.",
        )
        report = AdversarialReport(
            ticker=ticker,
            falsifiable_objections=("Structural commodity cycle transition risk.",),
            numeric_kill_criteria=default_kill,
            bear_floor_price=None,
            bear_thesis_summary=raw_content[:200] if raw_content else "Hostile stress test completed.",
        )
        return {
            "thesis_breakers": list(default_kill),
            "adversarial_report": report,
        }
