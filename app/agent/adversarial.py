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
    sec = state.get("sec_financials") or {}
    cust_conc = sec.get("customer_concentration") or {}

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
            "customer_concentration": cust_conc,
        },
        indent=2,
    )

    concentration_mandate = ""
    if cust_conc.get("has_concentration_risk"):
        top_pct = cust_conc.get("top_customer_pct")
        top_str = f"{top_pct}%" if top_pct is not None else ">= 10%"
        major_custs = cust_conc.get("major_customers") or []
        cust_details = ", ".join(f"{c.get('customer')}: {c.get('pct')}%" for c in major_custs) if major_custs else top_str
        concentration_mandate = f"""
CRITICAL RED-TEAM MANDATE (ASC 280-10-50-42 Customer Concentration):
SEC disclosures reveal severe customer concentration risk ({cust_details})!
You MUST formulate at least one explicit structural flaw/objection addressing customer pricing power, margin squeeze, dual-sourcing threats, or in-house substitution risk.
"""

    human_prompt = f"""Conduct a hostile short-seller red team attack on ${ticker}.

Verified Evidence and Facts gathered:
```json
{facts_payload}
```
{concentration_mandate}
Identify the 4 structural flaws, 2 numeric kill triggers, and realistic, empirically grounded bear floor price.
"""

    try:
        from app.agent.contracts import AdversarialAttackOutput
        from app.agent.model_runtime import invoke_structured_model

        output = invoke_structured_model(
            model,
            [
                SystemMessage(content=ADVERSARIAL_SYSTEM_PROMPT),
                HumanMessage(content=human_prompt),
            ],
            schema=AdversarialAttackOutput,
        )

        objections = tuple(str(x).strip() for x in output.falsifiable_objections if str(x).strip())
        kill_criteria = tuple(str(x).strip() for x in output.numeric_kill_criteria if str(x).strip())
        raw_floor = output.bear_floor_price
        try:
            bear_floor = float(raw_floor) if raw_floor is not None else None
        except (ValueError, TypeError):
            bear_floor = None

        # Deterministic parameter bridge: derive bear floor if model provided driver penalties
        curr_p = (market.get("quote") or {}).get("price")
        low_dcf = (((state.get("quant_report") or {}).get("valuation") or {}).get("fair_value_range") or {}).get("low")
        if bear_floor is None and curr_p and (output.revenue_cagr_delta_bps is not None or output.operating_margin_delta_bps is not None):
            try:
                r_pen = float(output.revenue_cagr_delta_bps or 0) / 10000.0
                m_pen = float(output.operating_margin_delta_bps or 0) / 10000.0
                calc_floor = round(float(curr_p) * max(0.20, 1.0 + r_pen * 1.5 + m_pen * 2.0), 2)
                if calc_floor < float(curr_p):
                    bear_floor = calc_floor
            except (ValueError, TypeError):
                pass
        elif bear_floor is None and low_dcf and float(low_dcf) > 0:
            bear_floor = float(low_dcf)

        summary = output.bear_thesis_summary or "Adversarial short-seller attack completed."

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
        logger.warning("Adversarial red-team structured model call failed: %s; falling back", exc)
        report = AdversarialReport(
            ticker=ticker,
            falsifiable_objections=(),
            numeric_kill_criteria=(),
            bear_floor_price=None,
            bear_thesis_summary=f"Red team attack failed: {exc}",
            status="unavailable",
            degradation_reasons=("model_unparseable",),
        )
        return {"thesis_breakers": [], "adversarial_report": report}
