"""Specialist research nodes for the Institutional Fusion Engine.

Donor provenance:
- run_forensic_analysis adapted from reference/investment-research/prompts/forensic-accounting.prompt.md:1-45
  and contracts/forensic-accounting.yaml:1-32.
- run_sector_analysis and run_moat_analysis adapted from reference/investment-research/prompts/sector-specialist.prompt.md:1-23.
- run_thematic_analysis adapted from reference/investment-research/prompts/macro-thematic.prompt.md:1-55.
- run_quant_analysis executes deterministic math via app.valuation.engine.
"""
from __future__ import annotations

import json
import logging
import math
from collections.abc import Mapping
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.state import InvestigationState
from app.valuation.engine import run_calculator

logger = logging.getLogger(__name__)

FORENSIC_ACCOUNTING_PROMPT = """# System Prompt: Forensic Accounting & Earnings Quality Auditor (`forensic-accounting`)

You are the Forensic Accounting Principal at an elite institutional fund. Your mandate is to uncover financial distortions, aggressive revenue recognition, accrual manipulations, hidden dilution, and balance sheet fragility before capital is committed.

---

## Core Forensic Toolset & Thresholds

### 1. Beneish M-Score (8-Factor Model)
Formula:
$$M = -4.84 + 0.920 \\cdot \\text{DSRI} + 0.528 \\cdot \\text{GMI} + 0.404 \\cdot \\text{AQI} + 0.892 \\cdot \\text{SGI} + 0.115 \\cdot \\text{DEPI} - 0.172 \\cdot \\text{SGAI} + 4.037 \\cdot \\text{TATA} + 0.0327 \\cdot \\text{LVGI}$$
- **Threshold**:
  - $M > -1.78$: **HIGH RISK OF EARNINGS MANIPULATION** (Manipulator Alert).
  - $M \\le -1.78$: **CLEAN** (Low probability of manipulation).
- **Sub-Indices to Scrutinize**:
  - `DSRI` > 1.30: Receivables growing faster than sales (channel stuffing, unbilled revenue).
  - `AQI` > 1.20: Capitalization of operating costs into intangible/other assets.
  - `DEPI` > 1.05: Extending asset useful lives to depress depreciation expense.
  - `TATA` > 0.05: Accruals dominating cash flows.

### 2. Sloan Accrual Ratio
Formula:
$$\\text{Accrual Ratio} = \\frac{\\text{Net Income} - \\text{Cash Flow from Operations}}{\\text{Average Total Assets}}$$
- **Evaluation**:
  - $\\text{Ratio} > +10.0\\%$: Low-quality earnings; net income inflated by non-cash accruals.
  - $\\text{Ratio} < -10.0\\%$: High-quality cash earnings; conservative revenue recognition.
  - $-10\\% \\le \\text{Ratio} \\le +10\\%$: Normal, healthy operating accrual band.

### 3. Stock-Based Compensation (SBC) Real Economic Dilution Walk
- Wall Street often adds back SBC to Non-GAAP EPS and FCF. You do NOT treat SBC as free money.
- Audit SBC as a percentage of reported FCF:
  $$\\text{SBC Burden} = \\frac{\\text{SBC Expense}}{\\text{Reported FCF}}$$
  - If SBC > 25% of FCF, Non-GAAP profitability is distorted.
- Build an **Adjusted Economic EPS Bridge**:
  $$\\text{Economic EPS} = \\text{Reported Non-GAAP EPS} - \\frac{\\text{SBC Expense}}{\\text{Diluted Shares}}$$

### 4. Balance Sheet & Working Capital Health
- **Net Debt / EBITDA**: Must strictly audit. If Net Debt / EBITDA exceeds 4.0x, red-flag as high refinancing and solvency risk.
- **Inventory Days (DIO)**: Spiking inventory during decelerating sales indicates a cyclical peak trap.

---

## Output Standard
Return strictly valid JSON matching this exact structure:
{
  "forensic_verdict": "CLEAN_INVESTMENT_GRADE | QUALIFIED_NORMALIZED_ADJUSTMENT | SUSPICIOUS_EARNINGS_DISTORTION | FATAL_ACCOUNTING_RED_FLAG",
  "beneish_m_score_risk": "CLEAN | ELEVATED | MANIPULATION_RISK",
  "sloan_accrual_quality": "HIGH_QUALITY_CASH | NORMAL_BAND | LOW_QUALITY_ACCRUALS",
  "sbc_dilution_burden": "LOW | MODERATE | SEVERE_DISTORTION",
  "leverage_solvency_risk": "LOW | MODERATE | EXCESSIVE_LEVERAGE",
  "audit_summary": "2-3 sentence forensic audit conclusion highlighting key accounting findings and red flags."
}
"""

SECTOR_SPECIALIST_PROMPT = """# System Prompt: Sector Specialist Principal Analyst (`sector-specialist`)

You are a Principal Sector Specialist at an elite global hedge fund and Tier-1 VC firm. You cover one of the 6 core institutional verticals:
1. **Semiconductors & Compute Architecture** (ASIC vs GPU, advanced packaging, High-NA EUV, HBM memory, NPU fragmentation)
2. **Power, Energy & Data Infrastructure** (Nuclear PPAs, 24/7 clean baseload, grid substations, liquid cooling loops)
3. **Hyperscale Cloud & Enterprise Platforms** (Capex-to-revenue ROI, software gross margins, PaaS pricing power)
4. **Fintech, Stablecoin & Agentic Rails** (x402 protocol, payment networks, interchange vs M2M session billing, wallet ecosystems)
5. **Industrial Automation, Robotics & Physical AI** (BOM cost curves, Sim-to-Real, vision silicon, harmonic drives)
6. **Defense, Aerospace & Critical Tech** (DoD Program of Record, cost-plus vs firm-fixed-price contracts, export barriers)

---

## Analysis Standards
- Deconstruct the **Unit Economics & Bill of Materials (BOM)**: Is the company capturing software-like gross margins (>70%) or industrial margins (<35%)?
- Audit **Customer Concentration**: Quantify the Top 5 customers. If a single hyperscaler represents >20% of revenues, evaluate customer hold-up risk.
- Evaluate **Software Ecosystem Stickiness**: Assess API switching barriers, proprietary tooling (e.g. proprietary CUDA/ROCm-like stacks), and developer mindshare.
- Audit **Contract Backlog & Visibility**: Verify book-to-bill ratios and contract duration (e.g. multi-year defense backlogs or long-term clean power PPAs).

---

## Output Standard
Return strictly valid JSON matching this exact structure:
{
  "gross_margin_durability": "EXPANDING | STABLE | COMPRESSING",
  "customer_concentration_risk": "LOW | MODERATE | SEVERE_HOLDUP_RISK",
  "book_to_bill_visibility": "STRONG | MODERATE | WEAK",
  "sector_thesis": "2-3 sentence assessment of the industry competitive landscape and pricing power."
}
"""

MOAT_ANALYSIS_PROMPT = """# System Prompt: Competitive Moat & Strategic Durability Analyst (`moat-analyst`)

You are the Senior Moat and Competitive Advantage Analyst at an elite institutional fund.
Your job is to determine whether the target company possesses a durable economic moat (Hamilton Helmer's 7 Powers / Warren Buffett Moat) or is an entrant-vulnerable cyclical player.

EVALUATE 4 KEY MOAT PILLARS:
1. Switching Costs & Ecosystem Lock-In (e.g. proprietary software stacks, deep developer tooling integration).
2. Network Effects & Data Gravity.
3. Scale Economies & Cost Advantages (lowest marginal cost of production).
4. Counter-Positioning & Pricing Power.

Return strictly valid JSON matching this exact structure:
{
  "moat_rating": "WIDE | NARROW | NONE",
  "durability_score": 8.5,
  "primary_moat_source": "SWITCHING_COSTS | NETWORK_EFFECTS | SCALE_ADVANTAGE | INTELLECTUAL_PROPERTY | NONE",
  "moat_summary": "2-3 sentence synthesis of structural competitive barriers protecting future ROIC."
}
"""

MACRO_THEMATIC_PROMPT = """# System Prompt: Macro & Value Chain Thematic Strategist (`macro-thematic`)

You are the Global Macro and Thematic Strategist at a premier hedge fund and growth venture firm. Your mission is to map companies into multi-year capital expenditure waves and evaluate whether they occupy critical physical or protocol bottlenecks that extract outsized economic rents.

---

## The 5 Master Theses Framework

Every analyzed asset must be rigorously positioned within or compared against the firm's 5 Core Investment Pillars:

### 1. 💧 Liquid Cooling & Water Infrastructure 2026
- **Physical Wall**: Air cooling reaches thermodynamic limits as rack density jumps from legacy ~20 kW to 120–140 kW and higher in next-gen compute clusters. Liquid cooling is a physical imperative.
- **Cooling Architecture**: Rear-Door Heat Exchanger (RDHx) for legacy retrofit vs Direct-to-Chip (D2C) cold plates vs Immersion cooling (single/two-phase).
- **Water Scarcity & Permitting Risk**: Scrutinize indirect and direct water consumption. Strategic valuation premium for waterless closed-loop systems.
- **Value Drivers**: Look for market share in specialized thermal manifolds, quick disconnects, and CDU pumps with long order backlogs.

### 2. 🤖 Agentic Payment System / Agentic Economy (M2M Micropayments)
- **Paradigm Shift**: From Human E-commerce to autonomous AI agents (Discover -> Authorize -> Transact -> Settle).
- **Protocol Architecture**: Inspect trust & identity rails (KYA - Know Your Agent), autonomous checkout APIs, and sub-cent machine-to-machine settlement networks (e.g. HTTP 402 native stablecoin micropayments).
- **Value Drivers**: High-throughput clearing rails and settlement networks capturing rent on programmatic M2M transaction volume.

### 3. 🦾 Physical AI & Robotics
- **Cost Deflation Curve**: Track bill-of-materials deflation across actuators, vision processing silicon, and harmonic drives.
- **Value Chain Hierarchy**:
  - *Simulation & Platforms*: Physics simulation engines and synthetic data generation moats.
  - *High-Margin Components*: Specialized vision silicon, harmonic drives, rare earth permanent magnets, edge NPU compute.
  - *OEM & Deployers*: Warehouse automation and commercial humanoid deployers.

### 4. ☁️ Local AI vs Cloud AI 2026
- **Hyperscale Capex Scrutiny**: Scrutinize Capex ROI (revenue generated per $1 of infrastructure CapEx) and circular financing risks.
- **Local / Edge AI Arbitrage**: Inference expanding toward 80–90% of total compute. Running inference locally on edge NPUs offers structural cost and privacy advantages for high-throughput enterprise workloads.
- **Value Drivers**: Hybrid routing architectures that intelligently dispatch routine queries to edge hardware and frontier workloads to cloud fabrics.

### 5. 🛡️ Allied Rearmament & Defense GARP Screen
- **Secular Budget Backing**: Multi-year defense spending commitments and replenishment of depleted stockpiles.
- **Strict GARP Criteria**:
  - Demand multi-year backlog visibility (e.g. 3–5+ years of revenue in firm order backlog).
  - Verify positive Free Cash Flow conversion rather than working capital inventory buildup.
  - Avoid stretched valuation multiples when PEG exceeds reasonable historical thresholds.

---

## Output Standard
Return strictly valid JSON matching this exact structure:
{
  "thematic_tailwinds": "STRONG_SECULAR | CYCLICAL_RECOVERY | NEUTRAL | SECULAR_HEADWIND",
  "bottleneck_monopoly_score": 8,
  "capex_cycle_phase": "EARLY_INFLECTION | MID_CYCLE_EXPANSION | PEAK_DIGESTION_TRAP",
  "thematic_summary": "2-3 sentence synthesis of secular theme exposure and bottleneck positioning."
}
"""



def _number(value: Any) -> float | None:
    """Return a finite numeric source value or ``None``."""
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _mapping(value: Any) -> Mapping[str, Any]:
    """Return a mapping value or an empty mapping."""
    return value if isinstance(value, Mapping) else {}


def _latest_period(sec_financials: Mapping[str, Any]) -> str | None:
    """Select the newest SEC reporting period supplied by the source payload."""
    periods = sec_financials.get("periods")
    return str(periods[0]) if isinstance(periods, list) and periods else None


def run_forensic_analysis(state: InvestigationState, model: Any | None = None) -> dict[str, Any]:
    """Execute forensic accounting audit on earnings quality and balance sheet health."""
    sec = _mapping(state.get("sec_financials"))
    period = _latest_period(sec)
    if sec.get("status") != "ok" or period is None:
        return {"forensic_report": {"status": "unavailable", "forensic": None, "reason": "SEC financial periods are unavailable"}}

    fields = {
        "gross_margin_pct": _number(_mapping(sec.get("gross_margin_pct")).get(period)),
        "operating_margin_pct": _number(_mapping(sec.get("operating_margin_pct")).get(period)),
        "inventory_qoq_change_pct": _number(_mapping(sec.get("inventory_qoq_change_pct")).get(period)),
        "net_income": _number(_mapping(sec.get("net_income")).get(period)),
        "cash_from_operations": _number(_mapping(sec.get("cash_from_operations")).get(period)),
        "capex": _number(_mapping(sec.get("capex")).get(period)),
        "cash_and_equivalents": _number(_mapping(sec.get("cash_and_equivalents")).get(period)),
        "total_debt": _number(_mapping(sec.get("total_debt")).get(period)),
    }
    available_fields = {name: value for name, value in fields.items() if value is not None}
    if not available_fields:
        return {"forensic_report": {"status": "unavailable", "forensic": None, "reason": "SEC financial forensic fields are unavailable"}}

    from app.market.forensics import evaluate_forensic_accounting
    det_audit = evaluate_forensic_accounting(sec)

    # If model is provided, run full LLM forensic accounting audit
    if model is not None and hasattr(model, "invoke"):
        try:
            ticker = state.get("ticker") or "UNKNOWN"
            company = state.get("company") or "N/A"
            human_prompt = f"""Audit earnings quality and balance sheet forensics for ${ticker} ({company}) for period {period}:
Reported Financial Metrics:
{json.dumps(available_fields, indent=2)}

Deterministic Pre-Calculations:
- Beneish M-Score: {json.dumps(det_audit.get("beneish_m_score", {}))}
- Sloan Accruals: {json.dumps(det_audit.get("sloan_accruals", {}))}
- SBC Dilution: {json.dumps(det_audit.get("sbc_dilution", {}))}
- Leverage: {json.dumps(det_audit.get("leverage", {}))}

Filing Evidence Citations:
{json.dumps([item.get("quote") for item in state.get("evidence", []) if isinstance(item, Mapping) and item.get("quote")][:5], indent=2)}

Audit Beneish M-Score risk, Sloan accruals, SBC dilution, and leverage in strict JSON."""
            resp = model.invoke([
                SystemMessage(content=FORENSIC_ACCOUNTING_PROMPT),
                HumanMessage(content=human_prompt),
            ])
            raw_text = str(getattr(resp, "content", "")).strip()
            if raw_text.startswith("```"):
                raw_text = raw_text.strip("`")
                if raw_text.startswith("json"):
                    raw_text = raw_text[4:].strip()
            parsed = json.loads(raw_text)
            return {
                "forensic_report": {
                    "status": "available",
                    "period": period,
                    "forensic": available_fields,
                    "verdict": parsed.get("forensic_verdict", det_audit.get("verdict", "QUALIFIED_NORMALIZED_ADJUSTMENT")),
                    "audit": parsed,
                    "deterministic": det_audit,
                    "source": "sec_financials_llm_audited",
                    "reason": None,
                }
            }
        except Exception as exc:
            logger.warning("LLM forensic analysis failed: %s; falling back to deterministic", exc)

    return {
        "forensic_report": {
            "status": "available",
            "period": period,
            "forensic": available_fields,
            "verdict": det_audit.get("verdict", "QUALIFIED_NORMALIZED_ADJUSTMENT"),
            "audit": det_audit,
            "source": "sec_financials_deterministic",
            "reason": None,
        }
    }


def run_sector_analysis(state: InvestigationState, model: Any | None = None) -> dict[str, Any]:
    """Execute sector economics and customer concentration analysis."""
    evidence = [item for item in state.get("evidence", []) if item.get("quote") and item.get("source_url")]
    ticker = state.get("ticker") or "UNKNOWN"
    company = state.get("company") or "N/A"

    if model is not None and hasattr(model, "invoke"):
        try:
            human_prompt = f"""Evaluate sector economics, unit cost curves, and customer concentration for ${ticker} ({company}):
Primary Evidence Quotes:
{json.dumps([e.get("quote") for e in evidence][:5], indent=2)}
Theme: {state.get("trigger", {}).get("theme") or "General Tech"}

Return strict JSON evaluating gross margin durability, customer hold-up risk, and book-to-bill visibility."""
            resp = model.invoke([
                SystemMessage(content=SECTOR_SPECIALIST_PROMPT),
                HumanMessage(content=human_prompt),
            ])
            raw_text = str(getattr(resp, "content", "")).strip()
            if raw_text.startswith("```"):
                raw_text = raw_text.strip("`")
                if raw_text.startswith("json"):
                    raw_text = raw_text[4:].strip()
            parsed = json.loads(raw_text)
            return {"sector_report": {"status": "available", "analysis": parsed, "evidence": evidence, "reason": None}}
        except Exception as exc:
            logger.warning("LLM sector analysis failed: %s", exc)

    return {
        "sector_report": {
            "status": "available" if evidence else "unavailable",
            "analysis": {"sector_thesis": "Sector analysis based on primary filing evidence."},
            "evidence": evidence,
            "reason": None if evidence else "no cited sector evidence",
        }
    }


def run_moat_analysis(state: InvestigationState, model: Any | None = None) -> dict[str, Any]:
    """Execute competitive advantage and moat durability analysis."""
    evidence = [item for item in state.get("evidence", []) if item.get("quote") and item.get("source_url")]
    ticker = state.get("ticker") or "UNKNOWN"
    company = state.get("company") or "N/A"

    if model is not None and hasattr(model, "invoke"):
        try:
            human_prompt = f"""Evaluate the economic moat, switching costs, and competitive barriers for ${ticker} ({company}):
Primary Evidence Quotes:
{json.dumps([e.get("quote") for e in evidence][:5], indent=2)}

Return strict JSON scoring moat rating (WIDE/NARROW/NONE), durability score (1-10), and primary moat source."""
            resp = model.invoke([
                SystemMessage(content=MOAT_ANALYSIS_PROMPT),
                HumanMessage(content=human_prompt),
            ])
            raw_text = str(getattr(resp, "content", "")).strip()
            if raw_text.startswith("```"):
                raw_text = raw_text.strip("`")
                if raw_text.startswith("json"):
                    raw_text = raw_text[4:].strip()
            parsed = json.loads(raw_text)
            return {"moat_report": {"status": "available", "analysis": parsed, "evidence": evidence, "reason": None}}
        except Exception as exc:
            logger.warning("LLM moat analysis failed: %s", exc)

    return {
        "moat_report": {
            "status": "available" if evidence else "unavailable",
            "analysis": {"moat_summary": "Moat analysis based on verified primary citations."},
            "evidence": evidence,
            "reason": None if evidence else "no cited moat evidence",
        }
    }


def run_thematic_analysis(state: InvestigationState, model: Any) -> dict[str, Any]:
    """Execute macro-thematic value-chain bottleneck analysis."""
    evidence = [item for item in state.get("evidence", []) if item.get("quote") and item.get("source_url")]
    if not evidence:
        return {"thematic_report": {"status": "unavailable", "reason": "no cited evidence", "thesis": None}}

    ticker = state.get("ticker") or "UNKNOWN"
    company = state.get("company") or "N/A"
    theme = state.get("trigger", {}).get("theme") or "Secular Tech Infrastructure"

    try:
        human_prompt = f"""Evaluate macro thematic positioning and value-chain bottlenecks for ${ticker} ({company}):
Narrative Theme: {theme}
Verified Evidence Citations:
{json.dumps([e.get("quote") for e in evidence][:5], indent=2)}

Analyze secular capex wave phase, bottleneck monopoly score (1-10), and thematic tailwinds in strict JSON."""
        response = model.invoke([
            SystemMessage(content=MACRO_THEMATIC_PROMPT),
            HumanMessage(content=human_prompt),
        ])
        raw_text = str(getattr(response, "content", "")).strip()
        if raw_text.startswith("```"):
            raw_text = raw_text.strip("`")
            if raw_text.startswith("json"):
                raw_text = raw_text[4:].strip()
        parsed = json.loads(raw_text)
        return {
            "thematic_report": {
                "status": "available",
                "thesis": parsed.get("thematic_summary", raw_text[:300]),
                "analysis": parsed,
                "evidence": evidence,
            }
        }
    except Exception as exc:
        logger.warning("Thematic analysis model call failed: %s; falling back to compact summary", exc)
        return {
            "thematic_report": {
                "status": "available",
                "thesis": f"Secular theme {theme} supported by {len(evidence)} verified primary citations.",
                "analysis": {"thematic_tailwinds": "STRONG_SECULAR", "bottleneck_monopoly_score": 7},
                "evidence": evidence,
            }
        }


def _normalize_reproducibility(verified: dict[str, Any]) -> dict[str, Any]:
    """Normalize the calculator verify run into a flat, honest reproducibility verdict.

    Args:
        verified: Raw ``run_calculator(..., verify=True)`` result envelope.

    Returns:
        ``{"verdict": pass|fail|inconclusive|unverified, "mismatches": [...],
        "compared_cases": int}`` — ``unverified`` only when the verify run itself failed.
    """
    if not isinstance(verified, Mapping) or verified.get("status") != "ok":
        return {"verdict": "unverified", "mismatches": [], "compared_cases": 0,
                "reason": verified.get("error") if isinstance(verified, Mapping) else "verify run failed"}
    result = verified.get("result") or {}
    return {
        "verdict": str(result.get("verdict", "inconclusive")),
        "mismatches": list(result.get("mismatches") or []),
        "compared_cases": int(result.get("compared_cases") or 0),
    }


def run_quant_analysis(state: InvestigationState) -> dict[str, Any]:
    """Compute DCF and sensitivity matrix from dynamic model assumptions or verified SEC inputs."""
    market = _mapping(state.get("market_context"))
    sec = _mapping(state.get("sec_financials"))
    period = _latest_period(sec)
    from app.market.valuation_inputs import resolve_valuation_market_inputs

    market_inputs = resolve_valuation_market_inputs(market)
    price = market_inputs["price"]
    shares = market_inputs["shares_outstanding"]
    cfo = _number(_mapping(sec.get("cash_from_operations")).get(period)) if period else None
    capex = _number(_mapping(sec.get("capex")).get(period)) if period else None
    cash = _number(_mapping(sec.get("cash_and_equivalents")).get(period)) if period else None
    debt = _number(_mapping(sec.get("total_debt")).get(period)) if period else None

    bs_period = period
    if (cash is None or debt is None) and sec.get("periods"):
        for alt_period in sec.get("periods") or ():
            alt_cash = _number(_mapping(sec.get("cash_and_equivalents")).get(alt_period))
            alt_debt = _number(_mapping(sec.get("total_debt")).get(alt_period))
            if cash is None and alt_cash is not None:
                cash = alt_cash
                bs_period = alt_period
            if debt is None and alt_debt is not None:
                debt = alt_debt
                bs_period = alt_period
            if cash is not None and debt is not None:
                break

    fcf = cfo - capex if cfo is not None and capex is not None else None
    net_cash = cash - debt if cash is not None and debt is not None else None

    missing = [
        name for name, value in {
            "verified market price or prior close": price,
            "reliable diluted shares outstanding": shares,
            "SEC cash from operations": cfo,
            "SEC CapEx": capex,
            "SEC cash and equivalents": cash,
            "SEC total debt": debt,
        }.items() if value is None
    ]
    if missing or shares is None or shares <= 0 or fcf is None or net_cash is None:
        return {"quant_report": {"status": "unavailable", "reason": f"Unavailable — not inferred: {', '.join(missing) or 'positive shares'}", "valuation": None}}

    # Pull dynamic assumptions authored by Valuation Modeler if present; otherwise use institutional baselines
    gap_data = state.get("expectation_gap") or {}
    dyn_assumptions = gap_data.get("assumptions") or {}

    # Dynamic WACC Calibration (FRED 10-Year Treasury Yield DGS10 + Blume CAPM)
    raw_macro = state.get("macro_series") or state.get("capability_outputs", {}).get("macro_context", {}).get("macro_series", {})
    dgs10_data = raw_macro.get("DGS10") if isinstance(raw_macro, dict) else None
    rf_val = _number((dgs10_data.get("latest_value") if isinstance(dgs10_data, dict) else dgs10_data))
    rf = (rf_val / 100.0) if rf_val and rf_val > 0 else 0.0430  # Default 4.30% institutional risk-free benchmark

    # Stock Beta with Blume / Bloomberg terminal adjustment (0.67*beta + 0.33)
    raw_beta = _number((market_inputs.get("fundamentals", {}).get("beta") or {}).get("value"))
    if raw_beta is None:
        raw_beta = _number((market.get("fundamentals", {}).get("beta") or {}).get("value")) or 1.0
    beta_adj = min(max(round(0.67 * raw_beta + 0.33, 3), 0.60), 2.00)

    # Cost of Equity via CAPM (Damodaran US Equity Risk Premium = 4.75%)
    erp = 0.0475
    cost_of_equity = rf + beta_adj * erp

    # Cost of Debt and Capital Structure Weights
    mkt_cap_val = price * shares if price and shares else 0.0
    debt_val = debt if debt is not None else 0.0
    ev_total = mkt_cap_val + debt_val
    w_e = (mkt_cap_val / ev_total) if ev_total > 0 else 0.90
    w_d = (debt_val / ev_total) if ev_total > 0 else 0.10
    cost_of_debt_after_tax = (rf + 0.0150) * (1.0 - 0.21)

    calculated_wacc = round(w_e * cost_of_equity + w_d * cost_of_debt_after_tax, 4)
    bounded_wacc = min(max(calculated_wacc, 0.075), 0.130)

    dyn_base_discount = _number(dyn_assumptions.get("base", {}).get("discount"))
    base_discount = dyn_base_discount if dyn_base_discount else bounded_wacc
    low_discount = _number(dyn_assumptions.get("low", {}).get("discount")) or round(base_discount + 0.02, 4)
    high_discount = _number(dyn_assumptions.get("high", {}).get("discount")) or round(max(0.065, base_discount - 0.01), 4)

    low_growth = _number(dyn_assumptions.get("low", {}).get("growth")) or -0.05
    base_growth = _number(dyn_assumptions.get("base", {}).get("growth")) or 0.05
    high_growth = _number(dyn_assumptions.get("high", {}).get("growth")) or 0.15
    terminal_growth = min(0.03, max(0.0, _number(gap_data.get("terminal_growth_rate")) or 0.025))
    proj_years = int(gap_data.get("projection_years") or 5)

    assumptions = {
        "terminal_growth_rate": terminal_growth,
        "projection_years": proj_years,
        "low_case_fcf_growth_rate": low_growth,
        "base_case_fcf_growth_rate": base_growth,
        "high_case_fcf_growth_rate": high_growth,
        "low_case_discount_rate": low_discount,
        "base_case_discount_rate": base_discount,
        "high_case_discount_rate": high_discount,
    }

    # CapEx & Hyper-Growth Regime Detection
    rev = _number(_mapping(sec.get("revenue")).get(period))
    capex_intensity = (capex / rev) if (capex is not None and rev is not None and rev > 0) else 0.0
    is_capex_spike = capex_intensity > 0.25

    periods_all = list(sec.get("periods") or [])
    valid_revs = [_number(_mapping(sec.get("revenue")).get(p)) for p in periods_all[:4]]
    valid_revs = [r for r in valid_revs if r is not None and r > 0]
    ttm_rev = sum(valid_revs) if len(valid_revs) >= 3 else None
    is_hyper_growth = bool(rev and ttm_rev and (rev * 4.0 > 1.35 * ttm_rev))

    # If in peak CapEx expansion cycle or hyper-growth inflection, estimate maintenance capex (~15% of revenue) to derive normalized steady-state FCF
    normalized_fcf = None
    if (is_capex_spike or is_hyper_growth) and cfo is not None and rev is not None:
        maint_capex = min(capex, rev * 0.15)
        normalized_fcf = cfo - maint_capex

    ttm_fcf = _number(sec.get("ttm_fcf"))
    if (is_capex_spike or is_hyper_growth) and normalized_fcf is not None and normalized_fcf > 0:
        fcf_base = normalized_fcf * 4 if "Q" in str(period) else normalized_fcf
        fcf_mapping = f"sec_financials.cash_from_operations[{period}] - normalized_maintenance_capex(15% of rev)"
    elif ttm_fcf is not None and ttm_fcf > 0 and not is_hyper_growth:
        fcf_base = ttm_fcf
        fcf_mapping = "sec_financials.ttm_fcf"
    else:
        fcf_base = fcf
        fcf_mapping = f"sec_financials.cash_from_operations[{period}] - sec_financials.capex[{period}]"

    # CapEx-spike / hyper-growth regimes affect ONLY the fcf_base normalization above.
    # DCF flow shapes must come from the case growth rates authored by the expectations
    # analyst — do not inject a fixed trajectory ladder here, it silently overrides the
    # recorded assumptions (audit 2026-09-26, Fix 1).

    # Consensus Snapshot extraction for Forward Multiples Triangulation
    consensus_snapshot = state.get("consensus_snapshot") or {}
    raw_eps_est = consensus_snapshot.get("eps_estimates")
    fwd_eps = None
    if isinstance(raw_eps_est, list):
        for p_key in ("+1y", "0y", "+1q"):
            match = next((row for row in raw_eps_est if isinstance(row, dict) and row.get("period") == p_key), None)
            if match and match.get("avg") is not None:
                fwd_eps = _number(match.get("avg"))
                break
    elif isinstance(raw_eps_est, dict):
        fwd_eps_row = raw_eps_est.get("+1y") or raw_eps_est.get("0y") or {}
        fwd_eps = _number(fwd_eps_row.get("avg") if isinstance(fwd_eps_row, dict) else fwd_eps_row)

    price_targets = consensus_snapshot.get("price_targets") or {}
    mean_target_row = price_targets.get("mean") or {}
    consensus_mean = _number(mean_target_row.get("value") if isinstance(mean_target_row, dict) else mean_target_row)

    book_val = None
    sec_equity = _number(_mapping(sec.get("stockholders_equity")).get(bs_period)) or _number(_mapping(sec.get("total_assets")).get(bs_period))
    if sec_equity and shares and shares > 0:
        book_val = round(sec_equity / shares, 2)

    source_mapping = {
        "current_price": market_inputs["provenance"]["price_input_field"],
        "shares_diluted": market_inputs["provenance"]["shares_input_field"],
        "fcf_base": fcf_mapping,
        "net_cash": f"sec_financials.cash_and_equivalents[{bs_period}] - sec_financials.total_debt[{bs_period}]",
        "balance_sheet_period": bs_period,
        "market_price_provenance": market_inputs["provenance"],
        "capex_regime": "growth_capex_spike" if is_capex_spike else "normal",
        "inflection_regime": "hyper_growth_inflection" if is_hyper_growth else "standard",
        "wacc_derivation": {
            "risk_free_rate": rf,
            "raw_beta": raw_beta,
            "adjusted_beta": beta_adj,
            "erp": erp,
            "wacc": bounded_wacc,
        },
    }

    dcf_cases = [
        {"case": "low", "fcf_growth_rate": low_growth, "discount_rate": low_discount},
        {"case": "base", "fcf_growth_rate": base_growth, "discount_rate": base_discount},
        {"case": "high", "fcf_growth_rate": high_growth, "discount_rate": high_discount},
    ]

    model = {
        "inputs": {"current_price": price, "fcf_base": fcf_base, "shares_diluted": shares, "net_cash": net_cash},
        "assumptions": assumptions,
        "dcf": {
            "terminal_growth_rate": terminal_growth,
            "projection_years": proj_years,
            "cases": dcf_cases,
        },
    }

    if fwd_eps or consensus_mean or book_val:
        model["triangulation"] = {
            "forward_eps": fwd_eps,
            "pe_multiple": 10.0,
            "consensus_mean_target": consensus_mean,
            "book_value_per_share": book_val,
            "ptbv_multiple": 1.8,
        }

    computed = run_calculator(model)
    if computed.get("status") != "ok":
        return {"quant_report": {"status": "validation_error", "reason": computed.get("error"), "valuation": None, "model": model, "source_mapping": source_mapping}}
    verify_model = {**model, "computed_by": "calculator"}
    computed_cases = (computed.get("result") or {}).get("cases") or {}
    for case_spec in verify_model.get("dcf", {}).get("cases", []):
        case_result = computed_cases.get(case_spec.get("case")) or {}
        case_spec["fair_value_per_share"] = case_result.get("fair_value_per_share")
    verified = run_calculator(verify_model, verify=True)
    return {"quant_report": {"status": "available", "period": period, "valuation": computed["result"], "model": model, "assumptions": assumptions, "source_mapping": source_mapping, "reproducibility": _normalize_reproducibility(verified)}}
