"""Michael Mauboussin reverse-expectations analysis and quantitative assumption modeling.

Donor provenance: adapted from reference/investment-research/prompts/valuation-modeler.prompt.md:1-30
and reference/investment-research/contracts/valuation-modeler.yaml:1-35.
Authors dynamic valuation assumptions and reverse-expectations gap analysis;
arithmetic is computed deterministically via app.valuation.engine.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.state import InvestigationState
from app.valuation.engine import run_calculator

logger = logging.getLogger(__name__)

EXPECTATIONS_SYSTEM_PROMPT = """# System Prompt: Quant & Deterministic Valuation Modeler (`valuation-modeler`)

You are the Senior Quantitative Valuation Modeler at an institutional investment fund. Your sole job is to translate qualitative business reality into rigorous, deterministic financial valuation models.

---

## Non-Negotiable Operational Axioms

1. **Zero LLM Token Arithmetic**:
   You author **assumptions only** (growth rates, discount rates/WACC, margin trajectories, capex curves, share counts).
   You NEVER perform math in LLM text generation. You execute the deterministic calculator to compute all DCF cash flows, terminal values, fair values per share, reverse DCFs, and sensitivity matrices.
2. **Strict Terminal Growth Ceiling**:
   `terminal_growth_rate` MUST NOT exceed 0.03 (3.0%). In long-run equilibrium, no corporate entity can perpetually compound faster than sovereign GDP. Values > 3.0% are rejected at Gate G3.
3. **Capex Cycles & Explicit Trajectories**:
   When companies are undergoing heavy capital expenditures (e.g. hyperscale AI data center buildouts, nuclear plant restarts, advanced fab packaging lines), TTM FCF is artificially depressed.
   Growing a depressed TTM FCF forward at a constant rate produces an absurdly low valuation. You MUST supply an explicit `fcf_trajectory` (e.g. `[1200, 2500, 4500, 6000, 7500]`) reflecting capex peak digestion and subsequent cash flow harvesting.
4. **Deterministic Reverse DCF**:
   Always run the Reverse DCF solver to reveal what growth rate $g_{\\text{implied}}$ the market is pricing into the current stock price.
   - If market prices in >25% FCF CAGR, highlight multiple derating risk.
   - If market prices in <5% FCF CAGR for a dominant moat, highlight asymmetric alpha opportunity.
5. **Sum-of-the-Parts (SOTP) for Conglomerates**:
   For multi-segment leaders (e.g. AMZN: AWS vs Retail; META: Family of Apps vs Reality Labs; CEG: Nuclear PPA fleet vs Calpine merchant gas), build an explicit SOTP segment valuation.
6. **Graham Number Calibration**:
   Compute the Graham Number $\\sqrt{22.5 \\times \\text{EPS} \\times \\text{BVPS}}$. For asset-light high-ROIC software or tech leaders, explain that Graham numbers are structurally depressed and assign low weight rather than using it as a false ceiling.

---

## Output Standard
Return strictly valid JSON matching this exact structure:
{
  "expectation_gap_verdict": "UNDERPRICED_CATALYST | ALREADY_PRICED_IN | OVERPRICED_EUPHORIA | UNCERTAIN_DISPERSION",
  "expectation_gap_summary": "Comprehensive 2-3 sentence analysis of what the market prices in vs. ground reality.",
  "implied_growth_interpretation": "Detailed commentary on the Reverse DCF implied growth rate.",
  "dcf_assumptions": {
    "terminal_growth_rate": 0.025,
    "projection_years": 5,
    "low_case": {
      "fcf_growth_rate": -0.05,
      "discount_rate": 0.12,
      "rationale": "Cyclical downturn and margin contraction..."
    },
    "base_case": {
      "fcf_growth_rate": 0.08,
      "discount_rate": 0.10,
      "rationale": "Steady execution matching baseline industry CAGR..."
    },
    "high_case": {
      "fcf_growth_rate": 0.18,
      "discount_rate": 0.09,
      "rationale": "High operating leverage on next-gen product ramp..."
    }
  }
}
"""



@dataclass(frozen=True)
class ExpectationGapAnalysis:
    """Structured reverse-expectations analysis produced by the Valuation Modeler."""

    verdict: str
    summary: str
    implied_growth_interpretation: str
    terminal_growth_rate: float
    projection_years: int
    low_case_growth: float
    low_case_discount: float
    base_case_growth: float
    base_case_discount: float
    high_case_growth: float
    high_case_discount: float

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for state persistence."""
        return {
            "verdict": self.verdict,
            "summary": self.summary,
            "implied_growth_interpretation": self.implied_growth_interpretation,
            "terminal_growth_rate": self.terminal_growth_rate,
            "projection_years": self.projection_years,
            "assumptions": {
                "low": {"growth": self.low_case_growth, "discount": self.low_case_discount},
                "base": {"growth": self.base_case_growth, "discount": self.base_case_discount},
                "high": {"growth": self.high_case_growth, "discount": self.high_case_discount},
            },
        }


def _run_preliminary_reverse_dcf(
    price: float | None,
    shares: float | None,
    fcf: float | None,
    net_cash: float | None,
) -> dict[str, Any] | None:
    """Run a deterministic preliminary reverse DCF solver via calculator.mjs."""
    if not price or price <= 0 or not shares or shares <= 0 or not fcf or fcf <= 0:
        return None
    model = {
        "inputs": {
            "current_price": price,
            "shares_diluted": shares,
            "fcf_base": fcf,
            "net_cash": net_cash or 0.0,
        },
        "assumptions": {
            "terminal_growth_rate": 0.025,
            "projection_years": 5,
            "low_case_fcf_growth_rate": -0.05,
            "base_case_fcf_growth_rate": 0.05,
            "high_case_fcf_growth_rate": 0.15,
            "low_case_discount_rate": 0.11,
            "base_case_discount_rate": 0.09,
            "high_case_discount_rate": 0.08,
        },
        "dcf": {
            "terminal_growth_rate": 0.025,
            "projection_years": 5,
            "cases": [
                {"case": "low", "fcf_growth_rate": -0.05, "discount_rate": 0.11},
                {"case": "base", "fcf_growth_rate": 0.05, "discount_rate": 0.09},
                {"case": "high", "fcf_growth_rate": 0.15, "discount_rate": 0.08},
            ],
        },
    }
    calc_res = run_calculator(model)
    if calc_res.get("status") == "ok":
        return calc_res.get("result", {}).get("reverse_dcf")
    return None


def run_expectations_analyst(state: InvestigationState, model: Any) -> dict[str, Any]:
    """Execute Michael Mauboussin reverse-expectations analysis.

    Args:
        state: Current investigation state with market context and consensus.
        model: Configured language model.

    Returns:
        State update populating expectation_gap and valuation assumptions.
    """
    ticker = state.get("ticker") or "UNKNOWN"
    company = state.get("company") or "N/A"
    market = state.get("market_context") or {}
    consensus = state.get("consensus_snapshot") or {}
    sec = state.get("sec_financials") or {}

    # Resolve only verified finite price and share observations for preliminary reverse DCF
    from app.market.valuation_inputs import resolve_valuation_market_inputs

    market_inputs = resolve_valuation_market_inputs(market)
    price = market_inputs["price"]
    shares = market_inputs["shares_outstanding"]

    periods = sec.get("periods") if isinstance(sec.get("periods"), list) else []
    period = periods[0] if periods else None
    cfo = None
    capex = None
    cash = None
    debt = None
    if period and isinstance(sec, Mapping):
        cfo = (sec.get("cash_from_operations") or {}).get(period)
        capex = (sec.get("capex") or {}).get(period)
        cash = (sec.get("cash_and_equivalents") or {}).get(period)
        debt = (sec.get("total_debt") or {}).get(period)

    try:
        fcf = float(cfo) - float(capex) if cfo is not None and capex is not None else None
        net_cash = float(cash) - float(debt) if cash is not None and debt is not None else 0.0
        price_f = price
        shares_f = shares
    except (TypeError, ValueError):
        fcf = None
        net_cash = 0.0
        price_f = None
        shares_f = None

    prelim_reverse_dcf = _run_preliminary_reverse_dcf(price_f, shares_f, fcf, net_cash)

    evidence_quotes = [
        item.get("quote") for item in state.get("evidence", [])
        if isinstance(item, Mapping) and item.get("quote")
    ][:5]

    human_prompt = f"""Investigate Michael Mauboussin's Expectation Gap for ${ticker} ({company}):

Market Data:
- Current Price: {price_f}
- Shares Outstanding: {shares_f}
- Base FCF (CFO - CapEx): {fcf}
- Net Cash (Cash - Debt): {net_cash}
- 20-day Volume Ratio: {(market.get("volume_ratio_20d") or {}).get("value")}

Consensus Estimates:
- Price Targets: {json.dumps(consensus.get("price_targets") or {}, default=str)}
- EPS Estimates: {json.dumps(consensus.get("eps_estimates") or [], default=str)}
- Revenue Estimates: {json.dumps(consensus.get("revenue_estimates") or [], default=str)}
- Ratings Breakdown: {json.dumps(consensus.get("ratings") or {}, default=str)}
- Earnings Proximity: {consensus.get("earnings_proximity_flag") or "UNKNOWN"}

Preliminary Deterministic Reverse DCF (from calculator.mjs):
{json.dumps(prelim_reverse_dcf or "Inapplicable (Missing or Non-Positive Base FCF)", indent=2, default=str)}

Verified Evidence Clues:
{json.dumps(evidence_quotes, indent=2, default=str)}

Analyze what is priced in vs. consensus forecasts and formulate the 3-case DCF parameters in valid JSON."""

    try:
        response = model.invoke([
            SystemMessage(content=EXPECTATIONS_SYSTEM_PROMPT),
            HumanMessage(content=human_prompt),
        ])
        raw_content = str(getattr(response, "content", "")).strip()
        # Strip potential markdown fences
        if raw_content.startswith("```"):
            raw_content = raw_content.strip("`")
            if raw_content.startswith("json"):
                raw_content = raw_content[4:].strip()
        parsed = json.loads(raw_content)

        dcf_assump = parsed.get("dcf_assumptions", {})
        term_growth = min(0.03, max(0.0, float(dcf_assump.get("terminal_growth_rate", 0.025))))
        proj_years = int(dcf_assump.get("projection_years", 5))
        low_case = dcf_assump.get("low_case", {})
        base_case = dcf_assump.get("base_case", {})
        high_case = dcf_assump.get("high_case", {})

        gap_analysis = ExpectationGapAnalysis(
            verdict=str(parsed.get("expectation_gap_verdict", "UNCERTAIN_DISPERSION")),
            summary=str(parsed.get("expectation_gap_summary", "Expectation gap analyzed.")),
            implied_growth_interpretation=str(parsed.get("implied_growth_interpretation", "")),
            terminal_growth_rate=term_growth,
            projection_years=proj_years,
            low_case_growth=float(low_case.get("fcf_growth_rate", -0.05)),
            low_case_discount=float(low_case.get("discount_rate", 0.12)),
            base_case_growth=float(base_case.get("fcf_growth_rate", 0.05)),
            base_case_discount=float(base_case.get("discount_rate", 0.10)),
            high_case_growth=float(high_case.get("fcf_growth_rate", 0.15)),
            high_case_discount=float(high_case.get("discount_rate", 0.09)),
        )
        return {
            "expectation_gap": gap_analysis.to_dict(),
            "expectation_gap_object": gap_analysis,
        }
    except Exception as exc:
        logger.warning("Expectations analyst model evaluation failed for %s: %s", ticker, exc)
        default_gap = {
            "verdict": "UNCERTAIN_DISPERSION",
            "summary": f"Expectation gap analysis defaulted due to model error: {exc}",
            "implied_growth_interpretation": "Model evaluation unavailable.",
            "terminal_growth_rate": 0.025,
            "projection_years": 5,
            "assumptions": {
                "low": {"growth": -0.05, "discount": 0.12},
                "base": {"growth": 0.03, "discount": 0.10},
                "high": {"growth": 0.08, "discount": 0.09},
            },
        }
        return {"expectation_gap": default_gap}
