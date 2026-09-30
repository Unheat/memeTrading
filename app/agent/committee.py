"""Investment Committee (CIO) deliberation and position sizing node.

Donor provenance: adapted from reference/investment-research/prompts/cio-ic.prompt.md:1-40,
contracts/cio-ic.yaml:1-38, and schemas/ic-verdict.schema.json.
Enforces 3:1 Asymmetry Hurdle, Passing Discipline, and Fractional Kelly sizing.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.adversarial import AdversarialReport
from app.agent.bull import BullReport
from app.agent.state import InvestigationState
from app.market.metrics import compute_fractional_kelly

logger = logging.getLogger(__name__)

# Tiered sizing governance (audit 2026-09-26, Batch D). Hurdles are config-driven via
# budget_state; these defaults keep the committee safe when no config was injected.
DEFAULT_ASYMMETRY_HURDLE = 3.0
DEFAULT_HALF_KELLY_RATIO = 5.0
DEFAULT_PAPER_TRADE_RATIO = 2.0
QUARTER_KELLY_FRACTION = 0.25
HALF_KELLY_FRACTION = 0.5
# Conviction-tier single-name caps: exceptional asymmetry with fully available
# debate reports earns a larger cap than the standard quarter-Kelly tier.
QUARTER_TIER_POSITION_CAP = 0.08
HALF_TIER_POSITION_CAP = 0.10

CIO_SYSTEM_PROMPT = """# System Prompt: Chief Investment Officer & Investment Committee Chair (`cio-ic`)

You are the Chief Investment Officer (CIO) and Chair of the Investment Committee at an elite multi-billion-dollar global hedge fund and Tier-1 venture capital firm. Your mandate is capital preservation, alpha generation, and uncompromising risk management.

You do not chase hype, retail fads, or management promises. You demand concrete data, verified filings, mathematical proof, and asymmetric risk/reward.

---

## Core Mandates & Governance Rules

### 1. The 3:1 Asymmetric Reward-to-Risk Rule
- You only approve long positions (`APPROVED_LONG`) if the upside to the Upside Anchor outweighs the downside to the Bear Floor by at least the configured `asymmetry_hurdle` (payload field; default 3.0 to 1):
  $$\\text{Reward-to-Risk Ratio} = \\frac{\\text{Upside Anchor} - \\text{Current Price}}{\\text{Current Price} - \\text{Bear Floor}} \\ge \\text{asymmetry_hurdle}$$
- The Upside Anchor is NOT necessarily a DCF output: cite its `upside_anchor_source`
  (consensus_mean, quant_fair_value, bull_target_price, or consensus_high_fallback)
  accurately in your `anchor_citation` field. Never describe a consensus target as a DCF value.
- If the ratio is below the hurdle, the trade is rejected, paper-traded when near-miss, or assigned to `Validation` awaiting a price pullback.

### 2. The Strict "Passing Discipline" (Saying NO to Hot Names)
You take pride in rejecting widely popular stocks when institutional fundamentals do not justify the risk. You enforce the firm's strict precedent:
- **Cyclical Commodity Producers**: When trading near cyclical margin peaks with CapEx intensity > 30% and impending competitor capacity additions, peak cycle multiples are an illusion. High CapEx burdens and commoditized pricing mean you PASS when trading near or above fair value with low margin of safety.
- **Multiple Compression & Entrant Cannibalization**: When a high-multiple tollbooth trades at 40x+ P/E while well-funded rivals secure regulatory or commercial qualification, future ROIC and margins will compress. PASS until multiple normalizes.
- **Excessive Leverage & Zero Margin of Error**: High Net Debt / EBITDA (> 4.0x) leaves the balance sheet fragile to debt refinancing cliffs and capex overruns. PASS.
- **Structural Price Wars & Regulatory Drag**: Domestic market share erosion, cloud price slashing, and sovereign regulatory intervention permanently cap multiples. PASS.
- **Scale Disadvantage**: Emerging sub-scale players lacking foundry scale and software ecosystems cannot compete with dominant platforms. PASS.

### 3. Conviction Tiers
- **`High 🔥🔥🔥`**: Irreplaceable bottleneck moat, >3:1 asymmetry, fortress balance sheet, structural secular tailwind.
- **`Medium 🔥🔥`**: Solid moat and catalysts, but near-term cycle transition or moderate customer concentration.
- **`Low 🔥` / `Validation`**: High multiple or unproven execution; waiting for operating margin confirmation and multiple digestion.
- **`🚫 Passed`**: Fails margin of safety, commodity cycle trap, or extreme leverage.

### 4. Position Sizing Mandate (Fractional Kelly Framework)
- Issue guidance on portfolio weight (typically 3–8% for High Conviction, 1–3% for Medium).
- Define the absolute maximum drawdown loss budget (e.g. hard stop if thesis breaks or stock declines 15% below entry).
- State the 2 numeric kill criteria that trigger immediate liquidation.

---

## Output Standard
Return strictly valid JSON matching this exact structure:
{
  "committee_verdict": "APPROVED_LONG | APPROVED_TACTICAL | VALIDATION_WATCH | PASSED_STRICT_DISCIPLINE | VETOED_BY_RISK",
  "conviction_tier": "HIGH CONVICTION 🔥🔥🔥 | MEDIUM CONVICTION 🔥🔥 | VALIDATION 🔥 | PASSED 🚫",
  "passes_3_to_1_hurdle": true,
  "passing_rationale": "Explicit institutional justification if passed/vetoed; otherwise null",
  "cio_deliberation_summary": "Comprehensive 3-4 sentence CIO deliberation synthesizing Bull vs Bear debate, margin of safety, and risk asymmetry."
}
"""



@dataclass(frozen=True)
class ICVerdict:
    """Formal Investment Committee deliberation and position sizing outcome."""

    ticker: str
    verdict: str
    conviction_tier: str
    reward_to_risk_ratio: float | None
    kelly_position_size_pct: float
    passing_discipline_checks: dict[str, str]
    cio_deliberation_summary: str
    upside_anchor: float | None = None
    upside_anchor_source: str = "missing"
    bear_anchor_source: str = "missing"
    anchor_citation: str = ""
    paper_trade: bool = False
    bear_floor: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "ticker": self.ticker,
            "verdict": self.verdict,
            "conviction_tier": self.conviction_tier,
            "reward_to_risk_ratio": self.reward_to_risk_ratio,
            "kelly_position_size_pct": self.kelly_position_size_pct,
            "passing_discipline_checks": dict(self.passing_discipline_checks),
            "cio_deliberation_summary": self.cio_deliberation_summary,
            "upside_anchor": self.upside_anchor,
            "upside_anchor_source": self.upside_anchor_source,
            "bear_anchor_source": self.bear_anchor_source,
            "anchor_citation": self.anchor_citation,
            "paper_trade": self.paper_trade,
            "bear_floor": self.bear_floor,
        }


def _report_status(report: Any) -> str:
    """Read the honest status of a bull/bear report object or dict.

    Args:
        report: Report object, dict, or None.

    Returns:
        One of ``available``, ``degraded``, ``unavailable``.
    """
    if report is None:
        return "unavailable"
    if isinstance(report, dict):
        return str(report.get("status", "available"))
    return str(getattr(report, "status", "available"))


def _specialist_reports_clean(state: Mapping[str, Any]) -> bool:
    """True when both debate anchors come from fully available specialist reports.

    Args:
        state: Current investigation state.

    Returns:
        False when any debate report is degraded or unavailable.
    """
    bull_status = _report_status(state.get("bull_report"))
    bear_status = _report_status(state.get("adversarial_report"))
    return "degraded" not in (bull_status, bear_status) and "unavailable" not in (bull_status, bear_status)


def run_investment_committee(state: InvestigationState, model: Any) -> dict[str, Any]:
    """Execute formal Investment Committee deliberation and position sizing.

    Args:
        state: Current investigation state with market data, consensus, and adversarial attack.
        model: Configured language model.

    Returns:
        State updates containing ic_verdict.
    """
    ticker = state.get("ticker") or "UNKNOWN"
    market = state.get("market_context") or {}
    consensus = state.get("consensus_snapshot") or {}
    adversarial: AdversarialReport | None = state.get("adversarial_report")
    bull_report: BullReport | None = state.get("bull_report")

    # 1. Evaluate Pre-Trade Hard Gates (Liquidity & Binary Risk)
    addv = (market.get("addv_20d") or {}).get("value")
    proximity_flag = str(consensus.get("earnings_proximity_flag") or "UNKNOWN").upper()

    passing_checks: dict[str, str] = {}
    is_liquid = (addv is not None and addv >= 1e6)
    passing_checks["liquidity_gate"] = "PASS" if is_liquid else "FAIL (< $1M ADDV / Illiquid)"

    is_blackout = (proximity_flag == "BLACKOUT_RISK")
    passing_checks["earnings_blackout_gate"] = "FAIL (Earnings <= 7d)" if is_blackout else "PASS"

    # Tiered sizing governance read from budget_state (config-driven, Batch D).
    budget_governance = state.get("budget_state") or {}
    asymmetry_hurdle = float(budget_governance.get("asymmetry_hurdle") or DEFAULT_ASYMMETRY_HURDLE)
    half_kelly_ratio = float(budget_governance.get("half_kelly_ratio") or DEFAULT_HALF_KELLY_RATIO)
    paper_trade_ratio = float(budget_governance.get("paper_trade_ratio") or DEFAULT_PAPER_TRADE_RATIO)

    # Pricing & Valuation Targets
    quote = market.get("quote") or {}
    raw_price = quote.get("price") or quote.get("value")
    current_price = float(raw_price) if raw_price and float(raw_price) > 0 else None

    price_targets = consensus.get("price_targets") or {}
    mean_target = price_targets.get("mean")
    base_target_val = mean_target.get("value") if isinstance(mean_target, dict) else mean_target
    base_target = float(base_target_val) if base_target_val and float(base_target_val) > 0 else None
    upside_anchor_source = "consensus_mean" if base_target else "missing"

    quant_val = (state.get("quant_report") or {}).get("valuation") or {}
    quant_fair_val = quant_val.get("fair_value") or (quant_val.get("fair_value_range") or {}).get("base")
    if quant_fair_val and float(quant_fair_val) > 0:
        if base_target is None or float(quant_fair_val) > base_target:
            base_target = max(base_target or 0.0, float(quant_fair_val))
            upside_anchor_source = "quant_fair_value"
        else:
            base_target = max(base_target or 0.0, float(quant_fair_val))

    if bull_report and bull_report.bull_target_price and current_price and bull_report.bull_target_price > current_price:
        if base_target is None or bull_report.bull_target_price > base_target:
            base_target = max(base_target or 0.0, bull_report.bull_target_price)
            upside_anchor_source = "bull_target_price"
        else:
            base_target = max(base_target or 0.0, bull_report.bull_target_price)

    # Symmetric numeric anchor fallback (audit 2026-09-26, Fix 6): when no anchor sits
    # above the price (e.g. a degraded bull report), escalate to the Street-high target
    # so the debate is measured against the bull side's best source-backed anchor.
    if current_price and (base_target is None or base_target <= current_price):
        high_target = price_targets.get("high")
        high_val = high_target.get("value") if isinstance(high_target, dict) else high_target
        if high_val and float(high_val) > current_price:
            base_target = float(high_val)
            upside_anchor_source = "consensus_high_fallback"

    raw_floor = adversarial.bear_floor_price if adversarial else None
    bear_floor = float(raw_floor) if raw_floor and float(raw_floor) > 0 else None
    bear_anchor_source = "red_team_bear_floor" if bear_floor else "missing"
    if not bear_floor:
        low_fv = (quant_val.get("fair_value_range") or {}).get("low")
        if low_fv and float(low_fv) > 0:
            bear_floor = float(low_fv)
            bear_anchor_source = "dcf_low_fallback"

    # Calculate 3:1 Reward-to-Risk Ratio
    ratio = None
    kelly_size = 0.0
    if current_price and base_target and bear_floor and base_target > current_price and bear_floor < current_price:
        upside_dollar = base_target - current_price
        # Enforce realistic minimum downside divisor (at least 3% of current price or $1.00)
        # to prevent divide-by-near-zero ratio inflation from micro downside spreads
        downside_dollar = max(current_price - bear_floor, current_price * 0.03, 1.0)
        ratio = round(upside_dollar / downside_dollar, 2)
        passing_checks["asymmetry_gate"] = "PASS" if ratio >= asymmetry_hurdle else f"FAIL ({ratio:.1f}x < {asymmetry_hurdle:.1f}x)"
        if ratio >= asymmetry_hurdle and is_liquid and not is_blackout:
            # Evidence-backed win probability estimation (Bayesian shrinkage in metrics.py)
            forensic_rep = state.get("forensic_report") or {}
            moat_rep = state.get("moat_report") or {}
            is_clean_forensic = "CLEAN" in str(forensic_rep.get("verdict") or "").upper()
            moat_rating = str((moat_rep.get("analysis") or {}).get("moat_rating") or "").lower()
            is_wide_moat = "wide" in moat_rating or "strong" in moat_rating
            has_severe_objections = bool(adversarial and len(adversarial.falsifiable_objections) >= 3)

            evidence_p = 0.50
            if is_clean_forensic:
                evidence_p += 0.04
            if is_wide_moat:
                evidence_p += 0.04
            if has_severe_objections:
                evidence_p -= 0.06

            # Tiered sizing: half-Kelly only at exceptional asymmetry with fully
            # available debate reports; quarter-Kelly otherwise (Batch D).
            half_tier = ratio >= half_kelly_ratio and _specialist_reports_clean(state)
            tier_fraction = HALF_KELLY_FRACTION if half_tier else QUARTER_KELLY_FRACTION
            kelly_size = compute_fractional_kelly(
                upside_pct=upside_dollar / current_price,
                downside_pct=downside_dollar / current_price,
                win_prob=evidence_p,
                fraction=tier_fraction,
                max_position_cap=HALF_TIER_POSITION_CAP if half_tier else QUARTER_TIER_POSITION_CAP,
                max_loss_budget=0.05,
            )
    else:
        if not current_price:
            passing_checks["price_gate"] = "FAIL (Missing or non-positive market price)"
        if not base_target:
            passing_checks["target_gate"] = "FAIL (Missing or non-positive upside target)"
        elif current_price and base_target <= current_price:
            passing_checks["target_gate"] = f"FAIL (Base fair value ${base_target:.2f} <= current price ${current_price:.2f})"
        if not bear_floor:
            passing_checks["bear_floor_gate"] = "FAIL (Missing or invalid bear downside floor)"
        elif current_price and bear_floor >= current_price:
            passing_checks["bear_floor_gate"] = f"FAIL (Bear floor ${bear_floor:.2f} >= current price ${current_price:.2f})"
        passing_checks["asymmetry_gate"] = f"FAIL (Reward-to-risk ratio does not clear 3:1 hurdle)"

    # Build comprehensive payload for CIO LLM deliberation.
    # Fix 10 (audit 2026-09-26): the upside anchor and the DCF fair value are reported
    # separately with their sources so the CIO prose cannot relabel a consensus target
    # as a DCF output.
    forensic = state.get("forensic_report") or {}
    thematic = state.get("thematic_report") or {}
    moat = state.get("moat_report") or {}
    prompt_payload = json.dumps(
        {
            "ticker": ticker,
            "current_price": current_price,
            "upside_anchor": base_target,
            "upside_anchor_source": upside_anchor_source,
            "dcf_base_fair_value": float(quant_fair_val) if quant_fair_val else None,
            "bear_floor_price": bear_floor,
            "bear_anchor_source": bear_anchor_source,
            "reward_to_risk_ratio": ratio,
            "asymmetry_hurdle": asymmetry_hurdle,
            "kelly_position_size_pct": f"{kelly_size:.1%}",
            "passing_discipline_checks": passing_checks,
            "forensic_verdict": forensic.get("verdict"),
            "moat_rating": (moat.get("analysis") or {}).get("moat_rating") if isinstance(moat.get("analysis"), dict) else None,
            "thematic_thesis": thematic.get("thesis"),
            "bull_thesis": bull_report.bull_thesis_summary if bull_report else "No bull model.",
            "bull_catalysts": list(bull_report.catalysts) if bull_report else [],
            "bull_target_price": bull_report.bull_target_price if bull_report else None,
            "bull_report_status": bull_report.status if bull_report else "unavailable",
            "operating_leverage_drivers": list(bull_report.operating_leverage_drivers) if bull_report else [],
            "adversarial_flaws": list(adversarial.falsifiable_objections) if adversarial else [],
            "adversarial_report_status": adversarial.status if adversarial else "unavailable",
            "numeric_kill_triggers": list(adversarial.numeric_kill_criteria) if adversarial else [],
        },
        indent=2,
    )

    cio_prompt = f"""Review the investment case for ${ticker}:
```json
{prompt_payload}
```
Deliberate as CIO, cite `upside_anchor_source` accurately in the required `anchor_citation` field, and return strictly valid JSON."""

    cio_verdict_str = "VALIDATION_WATCH"
    cio_conviction = "VALIDATION 🔥"
    cio_summary = "Committee deliberation completed."
    passing_rationale = None
    anchor_citation = ""

    try:
        response = model.invoke([
            SystemMessage(content=CIO_SYSTEM_PROMPT),
            HumanMessage(content=cio_prompt),
        ])
        raw_text = str(getattr(response, "content", "")).strip()
        if raw_text.startswith("```"):
            raw_text = raw_text.strip("`")
            if raw_text.startswith("json"):
                raw_text = raw_text[4:].strip()
        try:
            parsed = json.loads(raw_text)
            cio_verdict_str = str(parsed.get("committee_verdict", "VALIDATION_WATCH"))
            cio_conviction = str(parsed.get("conviction_tier", "VALIDATION 🔥"))
            cio_summary = str(parsed.get("cio_deliberation_summary", raw_text[:500]))
            passing_rationale = parsed.get("passing_rationale")
            anchor_citation = str(parsed.get("anchor_citation", ""))
        except Exception as parse_exc:
            cio_summary = raw_text[:500] if raw_text else f"CIO deliberation completed: {parse_exc}"
            if "APPROVED_LONG" in raw_text or "HIGH CONVICTION" in raw_text or (ratio and ratio >= asymmetry_hurdle and is_liquid and not is_blackout):
                confidence = state.get("confidence")
                if ratio and ratio >= asymmetry_hurdle and confidence is not None and confidence >= 0.70:
                    cio_verdict_str = "APPROVED_LONG_HIGH"
                    cio_conviction = "HIGH CONVICTION 🔥🔥🔥"
                elif ratio and ratio >= asymmetry_hurdle:
                    cio_verdict_str = "APPROVED_LONG_MEDIUM"
                    cio_conviction = "MEDIUM CONVICTION 🔥🔥"
    except Exception as exc:
        logger.warning("CIO LLM deliberation failed for %s: %s", ticker, exc)
        cio_summary = f"CIO deliberation generated under fallback: {exc}"

    # Tiered hard risk limits (Batch D):
    #   ratio < paper_trade_ratio            -> VALIDATION_WATCH (zero capital)
    #   paper_trade_ratio <= ratio < hurdle  -> PAPER_TRADE_WATCH (recorded, zero capital)
    #   ratio >= hurdle                      -> capital via quarter/half-Kelly tiers
    paper_trade = False
    if not is_liquid or is_blackout:
        cio_verdict_str = "PASSED_STRICT_DISCIPLINE"
        cio_conviction = "PASSED 🚫"
        kelly_size = 0.0
    elif ratio is None or ratio < paper_trade_ratio:
        cio_verdict_str = "VALIDATION_WATCH"
        cio_conviction = "VALIDATION 🔥"
        kelly_size = 0.0
    elif ratio < asymmetry_hurdle:
        cio_verdict_str = "PAPER_TRADE_WATCH"
        cio_conviction = "PAPER TRADE 📋"
        kelly_size = 0.0
        paper_trade = True
    elif ratio and ratio >= asymmetry_hurdle and cio_verdict_str in ("VALIDATION_WATCH", "PASSED_STRICT_DISCIPLINE", "PAPER_TRADE_WATCH"):
        confidence = state.get("confidence")
        if confidence is not None and confidence >= 0.70:
            cio_verdict_str = "APPROVED_LONG_HIGH"
            cio_conviction = "HIGH CONVICTION 🔥🔥🔥"
        else:
            cio_verdict_str = "APPROVED_LONG_MEDIUM"
            cio_conviction = "MEDIUM CONVICTION 🔥🔥"


    verdict_obj = ICVerdict(
        ticker=ticker,
        verdict=cio_verdict_str,
        conviction_tier=cio_conviction,
        reward_to_risk_ratio=ratio,
        kelly_position_size_pct=kelly_size,
        passing_discipline_checks=passing_checks,
        cio_deliberation_summary=cio_summary,
        upside_anchor=base_target,
        upside_anchor_source=upside_anchor_source,
        bear_anchor_source=bear_anchor_source,
        anchor_citation=anchor_citation,
        paper_trade=paper_trade,
        bear_floor=bear_floor,
    )
    return {"ic_verdict": verdict_obj}
