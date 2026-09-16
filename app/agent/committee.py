"""Investment Committee (CIO) deliberation and position sizing node.

Donor provenance: adapted from reference/investment-research/prompts/cio-ic.prompt.md:1-40,
contracts/cio-ic.yaml:1-38, and schemas/ic-verdict.schema.json.
Enforces 3:1 Asymmetry Hurdle, Passing Discipline, and Fractional Kelly sizing.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any
from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.adversarial import AdversarialReport
from app.agent.bull import BullReport
from app.agent.state import InvestigationState
from app.market.metrics import compute_fractional_kelly

logger = logging.getLogger(__name__)

CIO_SYSTEM_PROMPT = """# System Prompt: Chief Investment Officer & Investment Committee Chair (`cio-ic`)

You are the Chief Investment Officer (CIO) and Chair of the Investment Committee at an elite multi-billion-dollar global hedge fund and Tier-1 venture capital firm. Your mandate is capital preservation, alpha generation, and uncompromising risk management.

You do not chase hype, retail fads, or management promises. You demand concrete data, verified filings, mathematical proof, and asymmetric risk/reward.

---

## Core Mandates & Governance Rules

### 1. The 3:1 Asymmetric Reward-to-Risk Rule
- You only approve long positions (`APPROVED_LONG`) if the upside to Base Fair Value outweighs the downside to Bear Floor by at least **3.0 to 1**:
  $$\\text{Reward-to-Risk Ratio} = \\frac{\\text{Base DCF Fair Value} - \\text{Current Price}}{\\text{Current Price} - \\text{Bear DCF Fair Value}} \\ge 3.0$$
- If the ratio is below 3.0x, the trade is rejected or assigned to `Validation` awaiting a price pullback.

### 2. The Strict "Passing Discipline" (Saying NO to Hot Names)
You take pride in rejecting widely popular stocks when institutional fundamentals do not justify the risk. You enforce the firm's strict precedent:
- **Cyclical Commodity Traps (e.g. `MU` - Micron)**: Even if peak earnings or HBM memory demand look astronomical, peak cycle multiples are an illusion. High Capex burdens and commoditized pricing mean you PASS when trading near or above fair value with low margin of safety.
- **Multiple Compression & Entrant Cannibalization (e.g. `ISRG` - Intuitive Surgical)**: When a monopoly tollbooth trades at 40x+ P/E while well-funded rivals (Medtronic Hugo, J&J Ottava) secure FDA approval, future ROIC and margins will compress. PASS until multiple normalizes.
- **Excessive Leverage & Zero Margin of Error (e.g. `EQIX` - Equinix)**: High Net Debt / EBITDA (> 4.0x, and especially ~5.5x) leaves the balance sheet fragile to debt refinancing cliffs and capex overruns. PASS.
- **Structural Price Wars & Geopolitical Drag (e.g. `BABA` - Alibaba)**: Domestic market share erosion, cloud price slashing, and sovereign regulatory intervention permanently cap multiples. PASS.
- **Scale Disadvantage (e.g. `AMBA` - Ambarella)**: Emerging chip players lacking foundry scale and software ecosystems cannot compete with Qualcomm or Nvidia. PASS.

### 3. Conviction Tiers
- **`High 🔥🔥🔥`**: Irreplaceable bottleneck moat, >3:1 asymmetry, fortress balance sheet, structural secular tailwind (e.g. AMZN, META, CEG).
- **`Medium 🔥🔥`**: Solid moat and catalysts, but near-term cycle transition or moderate customer concentration (e.g. QCOM).
- **`Low 🔥` / `Validation`**: High multiple or unproven execution; waiting for operating margin confirmation and multiple digestion (e.g. VRT).
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
        }


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

    # Pricing & Valuation Targets
    quote = market.get("quote") or {}
    raw_price = quote.get("price") or quote.get("value")
    current_price = float(raw_price) if raw_price and float(raw_price) > 0 else None

    price_targets = consensus.get("price_targets") or {}
    mean_target = price_targets.get("mean")
    base_target_val = mean_target.get("value") if isinstance(mean_target, dict) else mean_target
    base_target = float(base_target_val) if base_target_val and float(base_target_val) > 0 else None
    if bull_report and bull_report.bull_target_price and current_price and bull_report.bull_target_price > current_price:
        base_target = max(base_target or 0.0, bull_report.bull_target_price)

    raw_floor = adversarial.bear_floor_price if adversarial else None
    bear_floor = float(raw_floor) if raw_floor and float(raw_floor) > 0 else None

    # Calculate 3:1 Reward-to-Risk Ratio
    ratio = None
    kelly_size = 0.0
    if current_price and base_target and bear_floor and base_target > current_price and bear_floor < current_price:
        upside_dollar = base_target - current_price
        downside_dollar = current_price - bear_floor
        ratio = round(upside_dollar / downside_dollar, 2)
        passing_checks["asymmetry_gate"] = "PASS" if ratio >= 3.0 else f"FAIL ({ratio:.1f}x < 3.0x)"
        if ratio >= 3.0 and is_liquid and not is_blackout:
            kelly_size = compute_fractional_kelly(
                upside_pct=upside_dollar / current_price,
                downside_pct=downside_dollar / current_price,
                win_prob=0.60,
                fraction=0.25,
                max_position_cap=0.08,
                max_loss_budget=0.05,
            )
    else:
        if not current_price:
            passing_checks["price_gate"] = "FAIL (Missing or non-positive market price)"
        if not base_target:
            passing_checks["target_gate"] = "FAIL (Missing or non-positive upside target)"
        if not bear_floor:
            passing_checks["bear_floor_gate"] = "FAIL (Missing or invalid bear downside floor)"
        passing_checks["asymmetry_gate"] = "FAIL (Incomplete price targets or floor)"

    # Build comprehensive payload for CIO LLM deliberation
    forensic = state.get("forensic_report") or {}
    thematic = state.get("thematic_report") or {}
    prompt_payload = json.dumps(
        {
            "ticker": ticker,
            "current_price": current_price,
            "base_target_price": base_target,
            "bear_floor_price": bear_floor,
            "reward_to_risk_ratio": ratio,
            "kelly_position_size_pct": f"{kelly_size:.1%}",
            "passing_discipline_checks": passing_checks,
            "forensic_verdict": forensic.get("verdict"),
            "thematic_thesis": thematic.get("thesis"),
            "bull_thesis": bull_report.bull_thesis_summary if bull_report else "No bull model.",
            "bull_catalysts": list(bull_report.catalysts) if bull_report else [],
            "operating_leverage_drivers": list(bull_report.operating_leverage_drivers) if bull_report else [],
            "adversarial_flaws": list(adversarial.falsifiable_objections) if adversarial else [],
            "numeric_kill_triggers": list(adversarial.numeric_kill_criteria) if adversarial else [],
        },
        indent=2,
    )

    cio_prompt = f"""Review the investment case for ${ticker}:
```json
{prompt_payload}
```
Deliberate as CIO and return strictly valid JSON."""

    cio_verdict_str = "VALIDATION_WATCH"
    cio_conviction = "VALIDATION 🔥"
    cio_summary = "Committee deliberation completed."
    passing_rationale = None

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
        except Exception as parse_exc:
            cio_summary = raw_text[:500] if raw_text else f"CIO deliberation completed: {parse_exc}"
            if "APPROVED_LONG" in raw_text or "HIGH CONVICTION" in raw_text or (ratio and ratio >= 3.0 and is_liquid and not is_blackout):
                confidence = state.get("confidence")
                if ratio and ratio >= 3.0 and confidence is not None and confidence >= 0.70:
                    cio_verdict_str = "APPROVED_LONG_HIGH"
                    cio_conviction = "HIGH CONVICTION 🔥🔥🔥"
                elif ratio and ratio >= 3.0:
                    cio_verdict_str = "APPROVED_LONG_MEDIUM"
                    cio_conviction = "MEDIUM CONVICTION 🔥🔥"
    except Exception as exc:
        logger.warning("CIO LLM deliberation failed for %s: %s", ticker, exc)
        cio_summary = f"CIO deliberation generated under fallback: {exc}"

    # Hard risk limits enforce zero capital allocation if hard gates fail
    if not is_liquid or is_blackout or ratio is None or ratio < 3.0:
        if not is_liquid or is_blackout:
            cio_verdict_str = "PASSED_STRICT_DISCIPLINE"
            cio_conviction = "PASSED 🚫"
        else:
            cio_verdict_str = "VALIDATION_WATCH"
            cio_conviction = "VALIDATION 🔥"
        kelly_size = 0.0
    elif ratio and ratio >= 3.0 and cio_verdict_str in ("VALIDATION_WATCH", "PASSED_STRICT_DISCIPLINE"):
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
    )
    return {"ic_verdict": verdict_obj}
