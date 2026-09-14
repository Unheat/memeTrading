"""Investment Committee (CIO) deliberation and position sizing node.

Donor provenance: adapted from reference/investment-research/prompts/cio-ic.prompt.md:1-40
and schemas/ic-verdict.schema.json.
Enforces 3:1 Asymmetry Hurdle, Passing Discipline, and Fractional Kelly sizing.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any
from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.adversarial import AdversarialReport
from app.agent.state import InvestigationState
from app.market.metrics import compute_fractional_kelly

logger = logging.getLogger(__name__)

CIO_SYSTEM_PROMPT = """You are the Chief Investment Officer (CIO) and Chair of the Investment Committee at an institutional equity hedge fund.
Your mandate is capital preservation, alpha generation, and uncompromising risk management.

You evaluate the uncompromised Bull Thesis against the Hostile Adversarial Bear Attack under:
1. The 3:1 Asymmetric Reward-to-Risk Rule: Upside must exceed downside by at least 3.0x.
2. The Strict Passing Discipline: Reject commodity peaks, multiple derating, and excessive leverage (>4.0x Net Debt/EBITDA).
3. Conviction Tiers:
   - APPROVED_LONG_HIGH (High Conviction 🔥🔥🔥)
   - APPROVED_LONG_MEDIUM (Medium Conviction 🔥🔥)
   - VALIDATION_WATCH (Validation 🔥)
   - PASSED_STRICT_DISCIPLINE (Passed 🚫)

Provide an executive CIO deliberation statement summarizing the capital allocation decision.
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

    :param state: Current investigation state with market data, consensus, and adversarial attack.
    :param model: Language model double or LLM instance.
    :returns: State updates with ic_verdict.
    """
    ticker = state.get("ticker") or "UNKNOWN"
    market = state.get("market_context") or {}
    consensus = state.get("consensus_snapshot") or {}
    adversarial: AdversarialReport | None = state.get("adversarial_report")

    # 1. Evaluate Pre-Trade Hard Gates (Liquidity & Binary Risk)
    addv = (market.get("addv_20d") or {}).get("value")
    cap_tier = str(market.get("cap_tier") or "unknown").lower()
    proximity_flag = str(consensus.get("earnings_proximity_flag") or "UNKNOWN").upper()

    passing_checks: dict[str, str] = {}
    is_liquid = (addv is not None and addv >= 5e6) and (cap_tier in ("mega", "large", "mid"))
    passing_checks["liquidity_gate"] = "PASS" if is_liquid else "FAIL (< $5M ADDV or Microcap)"

    is_blackout = (proximity_flag == "BLACKOUT_RISK")
    passing_checks["earnings_blackout_gate"] = "FAIL (Earnings <= 7d)" if is_blackout else "PASS"

    # Immediate rejection if hard gates fail
    if not is_liquid or is_blackout:
        reason = "Illiquid Microcap Trap" if not is_liquid else "Binary Earnings Blackout Risk"
        verdict = ICVerdict(
            ticker=ticker,
            verdict="PASSED_STRICT_DISCIPLINE",
            conviction_tier="PASSED 🚫",
            reward_to_risk_ratio=None,
            kelly_position_size_pct=0.0,
            passing_discipline_checks=passing_checks,
            cio_deliberation_summary=f"Mandatory Committee Veto: {reason}. Zero capital allocated.",
        )
        return {"ic_verdict": verdict}

    # 2. Evaluate 3:1 Asymmetry & Fractional Kelly Sizing
    quote = market.get("quote") or {}
    raw_price = quote.get("price")
    if raw_price is None or float(raw_price) <= 0:
        passing_checks["price_gate"] = "FAIL (Missing or non-positive market price)"
        verdict = ICVerdict(
            ticker=ticker,
            verdict="VALIDATION_WATCH",
            conviction_tier="VALIDATION 🔥",
            reward_to_risk_ratio=None,
            kelly_position_size_pct=0.0,
            passing_discipline_checks=passing_checks,
            cio_deliberation_summary=f"Missing market pricing for ${ticker}. Zero capital allocated.",
        )
        return {"ic_verdict": verdict}
    current_price = float(raw_price)

    price_targets = consensus.get("price_targets") or {}
    mean_target = price_targets.get("mean")
    if isinstance(mean_target, dict):
        base_target_val = mean_target.get("value")
    elif isinstance(mean_target, (int, float)):
        base_target_val = float(mean_target)
    else:
        base_target_val = None

    if base_target_val is None or float(base_target_val) <= current_price:
        passing_checks["target_gate"] = "FAIL (Missing or non-positive upside target)"
        verdict = ICVerdict(
            ticker=ticker,
            verdict="VALIDATION_WATCH",
            conviction_tier="VALIDATION 🔥",
            reward_to_risk_ratio=None,
            kelly_position_size_pct=0.0,
            passing_discipline_checks=passing_checks,
            cio_deliberation_summary=f"No verified upside target exceeding current price (${current_price:.2f}) for ${ticker}. Zero capital allocated.",
        )
        return {"ic_verdict": verdict}
    base_target = float(base_target_val)

    raw_floor = adversarial.bear_floor_price if adversarial else None
    if raw_floor is None or float(raw_floor) <= 0 or float(raw_floor) >= current_price:
        passing_checks["bear_floor_gate"] = "FAIL (Missing or invalid bear downside floor)"
        verdict = ICVerdict(
            ticker=ticker,
            verdict="VALIDATION_WATCH",
            conviction_tier="VALIDATION 🔥",
            reward_to_risk_ratio=None,
            kelly_position_size_pct=0.0,
            passing_discipline_checks=passing_checks,
            cio_deliberation_summary=f"Missing or invalid adversarial downside floor for ${ticker}. Zero capital allocated.",
        )
        return {"ic_verdict": verdict}
    bear_floor = float(raw_floor)

    upside_dollar = max(0.0, base_target - current_price)
    downside_dollar = max(0.01, current_price - bear_floor)
    ratio = round(upside_dollar / downside_dollar, 2)

    upside_pct = upside_dollar / current_price
    downside_pct = downside_dollar / current_price

    passing_checks["asymmetry_gate"] = "PASS" if ratio >= 3.0 else f"FAIL ({ratio:.1f}x < 3.0x)"

    if ratio >= 3.0:
        kelly_size = compute_fractional_kelly(
            upside_pct=upside_pct,
            downside_pct=downside_pct,
            win_prob=0.60,
            fraction=0.25,
            max_position_cap=0.08,
            max_loss_budget=0.05,
        )
    else:
        kelly_size = 0.0

    # 3. Deliberation via Model
    prompt_payload = json.dumps(
        {
            "ticker": ticker,
            "current_price": current_price,
            "base_target_price": base_target,
            "bear_floor_price": bear_floor,
            "reward_to_risk_ratio": ratio,
            "kelly_position_size_pct": f"{kelly_size:.1%}",
            "passing_discipline_checks": passing_checks,
            "adversarial_flaws": adversarial.falsifiable_objections if adversarial else [],
            "numeric_kill_triggers": adversarial.numeric_kill_criteria if adversarial else [],
        },
        indent=2,
    )

    cio_prompt = f"""Review the investment case for ${ticker}:
```json
{prompt_payload}
```
Issue the final Investment Committee verdict and capital allocation statement."""

    response = model.invoke([
        SystemMessage(content=CIO_SYSTEM_PROMPT),
        HumanMessage(content=cio_prompt),
    ])
    cio_text = getattr(response, "content", "")

    # Assign final conviction tier based on strict 3:1 hurdle
    confidence = state.get("confidence")
    if ratio >= 3.0 and confidence is not None and confidence >= 0.70:
        verdict_str = "APPROVED_LONG_HIGH"
        conviction = "HIGH CONVICTION 🔥🔥🔥"
    elif ratio >= 3.0:
        verdict_str = "APPROVED_LONG_MEDIUM"
        conviction = "MEDIUM CONVICTION 🔥🔥"
    else:
        verdict_str = "VALIDATION_WATCH"
        conviction = "VALIDATION 🔥"
        kelly_size = 0.0

    verdict_obj = ICVerdict(
        ticker=ticker,
        verdict=verdict_str,
        conviction_tier=conviction,
        reward_to_risk_ratio=ratio,
        kelly_position_size_pct=kelly_size,
        passing_discipline_checks=passing_checks,
        cio_deliberation_summary=cio_text[:500] if cio_text else "Committee deliberation completed.",
    )
    return {"ic_verdict": verdict_obj}
