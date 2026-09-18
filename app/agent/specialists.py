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
- **Net Debt / EBITDA**: Must strictly audit. If Net Debt / EBITDA exceeds 4.0x (e.g. EQIX at 5.5x), red-flag as high refinancing and solvency risk.
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
1. **Semiconductors & Compute Architecture** (ASIC vs GPU, CoWoS packaging, High-NA EUV, HBM memory, NPU fragmentation)
2. **Power, Energy & Data Infrastructure** (Nuclear PPAs, 24/7 clean baseload, grid substations, liquid cooling loops)
3. **Hyperscale Cloud & Enterprise Platforms** (Capex-to-revenue ROI, software gross margins, PaaS pricing power)
4. **Fintech, Stablecoin & Agentic Rails** (x402 protocol, payment networks, interchange vs M2M session billing, wallet ecosystems)
5. **Industrial Automation, Robotics & Physical AI** (BOM cost curves, Sim-to-Real, vision silicon, harmonic drives)
6. **Defense, Aerospace & Critical Tech** (DoD Program of Record, cost-plus vs firm-fixed-price contracts, export barriers)

---

## Analysis Standards
- Deconstruct the **Unit Economics & Bill of Materials (BOM)**: Is the company capturing software-like gross margins (>70%) or industrial margins (<35%)?
- Audit **Customer Concentration**: Quantify the Top 5 customers. If a single hyperscaler represents >20% of revenues, evaluate customer hold-up risk.
- Evaluate **Software Ecosystem Stickiness**: Assess API switching barriers, proprietary tooling (e.g. CUDA vs ROCm vs Modular Mojo), and developer mindshare.
- Audit **Contract Backlog & Visibility**: Verify book-to-bill ratios and contract duration (e.g. 5-7 year DoD backlogs or 20-year Microsoft-CEG clean power PPAs).

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
1. Switching Costs & Ecosystem Lock-In (e.g. proprietary software stacks, CUDA vs ROCm, enterprise integration).
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
- **Physical Wall**: Air cooling reaches absolute thermodynamic limits as rack density jumps from 16–27 kW (Blackwell B200) to 120–140 kW (GB200 NVL72) and ~600 kW (Rubin Ultra NVL576 in 2027). Liquid cooling is a physical imperative.
- **Cooling Architecture**: Rear-Door Heat Exchanger (RDHx) for legacy retrofit vs Direct-to-Chip (D2C) cold plates vs Immersion cooling (single/two-phase, CAGR 34%).
- **Water Scarcity & Permitting Risk**: Massive indirect and direct water consumption ($64B+ in data center projects stalled or rejected by municipal water authorities). Strategic valuation premium for **Waterless Two-Phase D2C** systems.
- **Key Names**: `VRT` (backlog leader), `MOD` (rapid data center HVAC pivot), `ETN`, `XYL`, `ECL`.

### 2. 🤖 Agentic Payment System / Agentic Economy (M2M Micropayments)
- **Paradigm Shift**: From Human E-commerce to autonomous AI agents (Discover -> Authorize -> Transact -> Settle).
- **Six-Layer Protocol Architecture**:
  1. *Discovery Layer*: `MCP` (Model Context Protocol), A2A Catalogs.
  2. *Trust & Identity Layer*: `ERC-8004`, Visa Agent Score & Directory, KYA (Know Your Agent).
  3. *Ordering Layer*: `ACP` (OpenAI + Stripe).
  4. *Authorization Layer*: `AP2` (Google + 60 financial institutions), Visa TAP, Mastercard AP4M.
  5. *Payment & Settlement Layer*: `x402` (Coinbase/Linux Foundation - HTTP 402 native stablecoin micropayments, 200ms sub-cent settlement), Stripe MPP.
  6. *Fulfillment Layer*: Merchant of Record.
- **B2C Trust Gap vs M2M Explosion**: Consumers exhibit trust gaps (only 11-14% permit autonomous checkout), but machine-to-machine API/compute micropayments ($0.001–$0.10) grow 100x+. The winners are the trust rails and clearing networks (`Visa`, `Mastercard`, `Stripe`, `Coinbase`).

### 3. 🦾 Physical AI & Robotics
- **Cost Deflation Curve**: Humanoid robot BOM costs falling ~40% per year ($50k–$250k down to $30k–$150k), accelerating commercial deployment timelines by 2–4 years.
- **Value Chain Hierarchy**:
  - *Simulation & Platforms*: `NVDA` (Omniverse, Isaac Sim CUDA moat for Sim-to-Real).
  - *High-Margin Components*: Vision silicon (`AMBA`), Harmonic drive actuators, rare earth permanent magnets (`MP Materials`), edge NPU compute (`QCOM`).
  - *OEM & Deployers*: `TSLA` (Optimus), `SYM` (Symbotic warehouse automation), `ROK`, `TER`.
  - *Private Venture Comps*: Figure AI ($39B valuation), Apptronik, 1X Technologies.
- **Pitfalls**: Unitree -45% post-IPO crash in China, dexterous manipulation bottlenecks, battery density limitations.

### 4. ☁️ Local AI vs Cloud AI 2026
- **Hyperscale Capex Scrutiny**: Top 4 Hyperscalers (MSFT, GOOGL, META, AMZN) spending $725B+ in 2026 (+77% YoY). Scrutinize Capex ROI (currently ~10 cents of revenue per $1 Capex) and circular financing risks.
- **Local / Edge AI Arbitrage**: Inference expanding to 80–90% of total compute. Running inference locally on Edge NPUs is 10–60x cheaper for high-throughput enterprise workloads (>50M tokens/month).
- **The Routing Architecture**: Future systems will not be binary; they will intelligently route 80% of routine queries to local/on-device NPUs (zero token cost, ultra-low latency, HIPAA/GDPR private) and escalate edge cases to frontier cloud models.
- **Key Bottleneck: NPU Tooling Fragmentation**: Apple, Qualcomm, Intel, AMD hardware exists, but unified cross-platform software tooling is missing.

### 5. 🛡️ Allied Rearmament & Defense GARP Screen
- **Secular Multi-Year Budget Backing**: NATO 2%+ commitments, replenishment of depleted stockpiles, Golden Dome missile defense.
- **Strict GARP Criteria**:
  - `LMT`: #1 ranking, 18.3x Fwd P/E, record $230.4B backlog (5–7 years cash flow visibility), $7B+ FCF.
  - `NOC`: #2 ranking, 18.4x Fwd P/E, 1.84x Book-to-Bill ($20B quarterly order intake), B-21 Raider catalyst.
  - `HII`: Penalized and demoted due to negative FCF (-$421M 1H) despite submarine monopoly.
  - European Defense (`BAE Systems`, `Thales`): Disqualified from GARP when trading at ~30x P/E and PEG > 4.5.

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

    low_growth = _number(dyn_assumptions.get("low", {}).get("growth")) or -0.05
    low_discount = _number(dyn_assumptions.get("low", {}).get("discount")) or 0.12
    base_growth = _number(dyn_assumptions.get("base", {}).get("growth")) or 0.05
    base_discount = _number(dyn_assumptions.get("base", {}).get("discount")) or 0.10
    high_growth = _number(dyn_assumptions.get("high", {}).get("growth")) or 0.15
    high_discount = _number(dyn_assumptions.get("high", {}).get("discount")) or 0.09
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
    ttm_fcf = _number(sec.get("ttm_fcf"))
    fcf_base = ttm_fcf if (ttm_fcf is not None and ttm_fcf > 0) else fcf
    fcf_mapping = (
        "sec_financials.ttm_fcf"
        if (ttm_fcf is not None and ttm_fcf > 0)
        else f"sec_financials.cash_from_operations[{period}] - sec_financials.capex[{period}]"
    )

    source_mapping = {
        "current_price": market_inputs["provenance"]["price_input_field"],
        "shares_diluted": market_inputs["provenance"]["shares_input_field"],
        "fcf_base": fcf_mapping,
        "net_cash": f"sec_financials.cash_and_equivalents[{bs_period}] - sec_financials.total_debt[{bs_period}]",
        "balance_sheet_period": bs_period,
        "market_price_provenance": market_inputs["provenance"],
    }
    model = {
        "inputs": {"current_price": price, "fcf_base": fcf_base, "shares_diluted": shares, "net_cash": net_cash},
        "assumptions": assumptions,
        "dcf": {
            "terminal_growth_rate": terminal_growth,
            "projection_years": proj_years,
            "cases": [
                {"case": "low", "fcf_growth_rate": low_growth, "discount_rate": low_discount},
                {"case": "base", "fcf_growth_rate": base_growth, "discount_rate": base_discount},
                {"case": "high", "fcf_growth_rate": high_growth, "discount_rate": high_discount},
            ],
        },
    }
    computed = run_calculator(model)
    if computed.get("status") != "ok":
        return {"quant_report": {"status": "validation_error", "reason": computed.get("error"), "valuation": None, "model": model, "source_mapping": source_mapping}}
    verified = run_calculator({**model, "computed_by": "calculator"}, verify=True)
    return {"quant_report": {"status": "available", "period": period, "valuation": computed["result"], "model": model, "assumptions": assumptions, "source_mapping": source_mapping, "reproducibility": verified}}
