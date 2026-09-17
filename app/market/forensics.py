"""Deterministic forensic accounting calculations.

Donor provenance: adapted from reference/investment-research contracts/forensic-accounting.yaml
and app/valuation/calculator.mjs:240-310 (Beneish 8-factor M-Score and Sloan Accrual Ratio).
"""
from __future__ import annotations

from collections.abc import Mapping
import math
from typing import Any


def _round(val: float | None, digits: int = 4) -> float | None:
    """Safely round floating point values."""
    if val is None or math.isnan(val) or math.isinf(val):
        return None
    return round(float(val), digits)


def compute_beneish_m_score(
    dsri: float = 1.0,
    gmi: float = 1.0,
    aqi: float = 1.0,
    sgi: float = 1.0,
    depi: float = 1.0,
    sgai: float = 1.0,
    tata: float = 0.0,
    lvgi: float = 1.0,
) -> dict[str, Any]:
    """Calculate the 8-factor Beneish M-Score for earnings manipulation detection.

    Formula:
      M = -4.84 + 0.920*DSRI + 0.528*GMI + 0.404*AQI + 0.892*SGI +
          0.115*DEPI - 0.172*SGAI + 4.037*TATA + 0.0327*LVGI

    Threshold:
      M > -1.78 indicates high probability of accounting manipulation.
    """
    m_score = (
        -4.84
        + 0.920 * dsri
        + 0.528 * gmi
        + 0.404 * aqi
        + 0.892 * sgi
        + 0.115 * depi
        - 0.172 * sgai
        + 4.037 * tata
        + 0.0327 * lvgi
    )

    is_manipulator = m_score > -1.78
    return {
        "m_score": _round(m_score, 3),
        "is_manipulator_probability_high": is_manipulator,
        "threshold": -1.78,
        "verdict": "HIGH_RISK_EARNINGS_MANIPULATION" if is_manipulator else "CLEAN_LOW_MANIPULATION_RISK",
        "indices": {
            "dsri": _round(dsri, 3),
            "gmi": _round(gmi, 3),
            "aqi": _round(aqi, 3),
            "sgi": _round(sgi, 3),
            "depi": _round(depi, 3),
            "sgai": _round(sgai, 3),
            "tata": _round(tata, 3),
            "lvgi": _round(lvgi, 3),
        },
    }


def compute_sloan_accrual(
    net_income: float | None,
    cfo: float | None,
    total_assets: float | None,
    prev_total_assets: float | None = None,
) -> dict[str, Any] | None:
    """Calculate Sloan Accrual Ratio to assess cash conversion quality.

    Formula:
      Accrual Ratio = (Net Income - Cash Flow from Operations) / Average Total Assets
    """
    if net_income is None or cfo is None or not total_assets or total_assets <= 0:
        return None

    avg_assets = (total_assets + prev_total_assets) / 2.0 if prev_total_assets and prev_total_assets > 0 else float(total_assets)
    accrual = (net_income - cfo) / avg_assets

    if accrual > 0.10:
        quality_band = "LOW_EARNINGS_QUALITY (Aggressive Accruals)"
    elif accrual < -0.10:
        quality_band = "VERY_HIGH_EARNINGS_QUALITY (Conservative / Heavy Cash Conversion)"
    else:
        quality_band = "NORMAL_EARNINGS_QUALITY"

    return {
        "accrual_ratio": _round(accrual, 4),
        "accrual_pct": f"{round(accrual * 100, 2)}%",
        "quality_band": quality_band,
    }


def compute_sbc_dilution(
    sbc_expense: float | None,
    fcf: float | None,
) -> dict[str, Any] | None:
    """Evaluate Stock-Based Compensation burden relative to Free Cash Flow."""
    if sbc_expense is None or fcf is None or fcf <= 0:
        return None

    ratio = sbc_expense / fcf
    burden = "LOW" if ratio < 0.15 else ("MODERATE" if ratio <= 0.25 else "HIGH_DILUTION_BURDEN")
    return {
        "sbc_as_pct_of_fcf": _round(ratio * 100.0, 2),
        "sbc_dilution_ratio": _round(ratio, 4),
        "burden_level": burden,
    }


def compute_leverage_profile(
    total_debt: float | None,
    cash_and_equivalents: float | None,
    operating_income: float | None = None,
) -> dict[str, Any]:
    """Evaluate balance sheet leverage and net cash cushion."""
    debt = float(total_debt or 0.0)
    cash = float(cash_and_equivalents or 0.0)
    net_debt = debt - cash
    is_net_cash = net_debt < 0

    net_debt_to_ebit = None
    if operating_income and operating_income > 0:
        net_debt_to_ebit = _round(net_debt / operating_income, 2)

    return {
        "total_debt": debt,
        "cash_and_equivalents": cash,
        "net_debt": net_debt,
        "is_net_cash_positive": is_net_cash,
        "net_debt_to_operating_income": net_debt_to_ebit,
        "leverage_risk": "EXCESSIVE_LEVERAGE" if (net_debt_to_ebit and net_debt_to_ebit > 4.0) else ("LOW_OR_NET_CASH" if is_net_cash else "MODERATE"),
    }


def evaluate_forensic_accounting(sec_financials: Mapping[str, Any] | None) -> dict[str, Any]:
    """Execute complete deterministic forensic audit from available SEC financials.

    Returns:
        Structured audit dictionary with Beneish M-Score, Sloan Accruals, SBC Dilution,
        Leverage profile, and overall forensic verdict.
    """
    if not sec_financials or not isinstance(sec_financials, Mapping):
        return {
            "status": "inconclusive",
            "verdict": "INCONCLUSIVE_INSUFFICIENT_DATA",
            "missing_inputs": ["sec_financials"],
            "reason": "SEC financials mapping is missing or empty.",
        }

    periods = sec_financials.get("periods") or []
    if not periods:
        return {
            "status": "inconclusive",
            "verdict": "INCONCLUSIVE_INSUFFICIENT_DATA",
            "missing_inputs": ["periods"],
            "reason": "No financial statement periods available in SEC data.",
        }

    curr_p = str(periods[0])
    prev_p = str(periods[1]) if len(periods) > 1 else None

    def _val(field: str, p: str | None) -> float | None:
        if not p:
            return None
        series = sec_financials.get(field)
        if isinstance(series, Mapping):
            v = series.get(p)
            try:
                return float(v) if v is not None else None
            except (ValueError, TypeError):
                return None
        return None

    # Extract primary financial fields
    cfo = _val("cash_from_operations", curr_p)
    capex = _val("capex", curr_p) or 0.0
    fcf = (cfo - capex) if cfo is not None else None
    net_income = _val("net_income", curr_p)
    total_debt = _val("total_debt", curr_p)
    cash = _val("cash_and_equivalents", curr_p)
    op_inc = _val("operating_income", curr_p)
    total_assets = _val("total_assets", curr_p) or _val("assets", curr_p)
    prev_assets = _val("total_assets", prev_p) or _val("assets", prev_p)
    sbc = _val("stock_based_compensation", curr_p) or _val("sbc", curr_p)

    # 1. Sloan Accruals
    sloan = compute_sloan_accrual(net_income, cfo, total_assets, prev_assets)

    # 2. SBC Dilution
    sbc_audit = compute_sbc_dilution(sbc, fcf)

    # 3. Leverage Profile
    leverage = compute_leverage_profile(total_debt, cash, op_inc)

    # 4. Beneish M-Score Indices
    # If consecutive periods exist, compute Gross Margin Index and Sales Growth Index
    rev_curr = _val("revenue", curr_p)
    rev_prev = _val("revenue", prev_p)
    gm_curr = _val("gross_margin_pct", curr_p)
    gm_prev = _val("gross_margin_pct", prev_p)

    sgi = (rev_curr / rev_prev) if (rev_curr and rev_prev and rev_prev > 0) else 1.0
    gmi = (gm_prev / gm_curr) if (gm_prev and gm_curr and gm_curr > 0) else 1.0
    tata = ((op_inc - cfo) / total_assets) if (op_inc is not None and cfo is not None and total_assets and total_assets > 0) else 0.0

    beneish = compute_beneish_m_score(
        sgi=sgi,
        gmi=gmi,
        tata=tata,
    )

    # Missing inputs audit
    missing = []
    if total_assets is None:
        missing.append("total_assets")
    if sbc is None:
        missing.append("stock_based_compensation")
    if rev_prev is None:
        missing.append("prior_period_revenue")

    # Determine overall forensic verdict
    red_flags = []
    if beneish.get("is_manipulator_probability_high"):
        red_flags.append(f"Beneish M-Score flagged ({beneish.get('m_score')} > -1.78)")
    if sloan and "Aggressive Accruals" in sloan.get("quality_band", ""):
        red_flags.append(f"Aggressive accruals: Net Income significantly outpaces Operating Cash Flow ({sloan.get('accrual_pct')})")
    if sbc_audit and sbc_audit.get("burden_level") == "HIGH_DILUTION_BURDEN":
        red_flags.append(f"High SBC dilution burden: SBC accounts for {sbc_audit.get('sbc_as_pct_of_fcf')}% of Free Cash Flow")
    if leverage.get("leverage_risk") == "EXCESSIVE_LEVERAGE":
        red_flags.append(f"Excessive debt burden: Net Debt to Operating Income exceeds 4.0x ({leverage.get('net_debt_to_operating_income')}x)")

    if beneish.get("is_manipulator_probability_high") and len(red_flags) >= 2:
        verdict = "UNACCEPTABLE_AGGRESSIVE_ACCOUNTING"
        status = "ok"
    elif red_flags:
        verdict = "ELEVATED_SCRUTINY_REQUIRED"
        status = "ok"
    else:
        verdict = "QUALIFIED_NORMALIZED_ADJUSTMENT"
        status = "ok" if not missing else "partial"

    return {
        "status": status,
        "period": curr_p,
        "verdict": verdict,
        "beneish_m_score": beneish,
        "sloan_accruals": sloan,
        "sbc_dilution": sbc_audit,
        "leverage": leverage,
        "red_flags": red_flags,
        "missing_inputs": missing,
    }
