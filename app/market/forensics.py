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

    Formula (published eight-variable model, Beneish 1999):
      M = -4.84 + 0.920*DSRI + 0.528*GMI + 0.404*AQI + 0.892*SGI +
          0.115*DEPI - 0.172*SGAI + 4.679*TATA - 0.327*LVGI

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
        + 4.679 * tata
        - 0.327 * lvgi
    )

    # Cash-confirmed hypergrowth adjustment:
    # If revenue is growing rapidly (SGI > 1.25) but total accruals are non-positive (TATA <= 0.0),
    # meaning earnings are backed by real cash conversion (CFO >= Net Income/Operating Income),
    # evaluate organic growth adjusted M-Score by capping SGI at 1.25 to prevent false-positive fraud flags.
    organic_growth_confirmed = bool(sgi > 1.25 and tata <= 0.0)
    effective_sgi = min(sgi, 1.25) if organic_growth_confirmed else sgi
    adjusted_m_score = (
        -4.84
        + 0.920 * dsri
        + 0.528 * gmi
        + 0.404 * aqi
        + 0.892 * effective_sgi
        + 0.115 * depi
        - 0.172 * sgai
        + 4.679 * tata
        - 0.327 * lvgi
    )

    # Beneish 5-variable model (Beneish 1997, cutoff -2.22)
    m5_score = -6.065 + 0.823 * dsri + 0.906 * gmi + 0.593 * aqi + 0.717 * sgi + 0.107 * depi

    is_manipulator = m_score > -1.78
    if is_manipulator and organic_growth_confirmed and adjusted_m_score <= -1.78:
        # Overrule false positive: hypergrowth is verified by cash conversion
        is_manipulator = False
        verdict = "ORGANIC_GROWTH_CONFIRMED_CLEAN"
    elif is_manipulator:
        verdict = "HIGH_RISK_EARNINGS_MANIPULATION"
    else:
        verdict = "CLEAN_LOW_MANIPULATION_RISK"

    return {
        "m_score": _round(m_score, 3),
        "adjusted_m_score": _round(adjusted_m_score, 3),
        "m5_score": _round(m5_score, 3),
        "organic_growth_confirmed": organic_growth_confirmed,
        "is_manipulator_probability_high": is_manipulator,
        "threshold": -1.78,
        "verdict": verdict,
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


def compute_altman_z_score(
    working_capital: float | None,
    retained_earnings: float | None,
    ebit: float | None,
    market_cap: float | None,
    total_liabilities: float | None,
    sales: float | None,
    total_assets: float | None,
    is_manufacturing: bool = True,
) -> dict[str, Any] | None:
    """Calculate quantitative Altman Z-Score / Z''-Score for balance sheet distress risk.

    Manufacturing formula (Altman 1968):
      Z = 1.2*X1 + 1.4*X2 + 3.3*X3 + 0.6*X4 + 0.999*X5
      Cutoffs: Z > 2.99 Safe, 1.81 <= Z <= 2.99 Grey, Z < 1.81 Distress.

    Non-manufacturing / tech / service formula (Altman 1993, Z''-Score):
      Z'' = 6.56*X1 + 3.26*X2 + 6.72*X3 + 1.05*X4
      Cutoffs: Z'' > 2.60 Safe, 1.10 <= Z'' <= 2.60 Grey, Z'' < 1.10 Distress.
    """
    if total_assets is None or total_assets <= 0:
        return None

    x1 = (working_capital or 0.0) / total_assets
    x2 = (retained_earnings or 0.0) / total_assets
    x3 = (ebit or 0.0) / total_assets
    tot_liab = total_liabilities if (total_liabilities and total_liabilities > 0) else (total_assets * 0.5)
    x4 = (market_cap or (total_assets - tot_liab)) / tot_liab
    x5 = (sales or 0.0) / total_assets

    if is_manufacturing:
        z_score = 1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * x4 + 0.999 * x5
        if z_score > 2.99:
            zone = "SAFE_ZONE"
            distress_risk = "LOW"
        elif z_score >= 1.81:
            zone = "GREY_ZONE"
            distress_risk = "MODERATE"
        else:
            zone = "DISTRESS_ZONE"
            distress_risk = "HIGH"
        threshold_safe = 2.99
        threshold_distress = 1.81
    else:
        z_score = 6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4
        if z_score > 2.60:
            zone = "SAFE_ZONE"
            distress_risk = "LOW"
        elif z_score >= 1.10:
            zone = "GREY_ZONE"
            distress_risk = "MODERATE"
        else:
            zone = "DISTRESS_ZONE"
            distress_risk = "HIGH"
        threshold_safe = 2.60
        threshold_distress = 1.10

    return {
        "z_score": _round(z_score, 2),
        "zone": zone,
        "distress_risk": distress_risk,
        "model_variant": "manufacturing_5_factor" if is_manufacturing else "service_tech_4_factor",
        "threshold_safe": threshold_safe,
        "threshold_distress": threshold_distress,
        "components": {
            "x1_working_capital_to_assets": _round(x1, 4),
            "x2_retained_earnings_to_assets": _round(x2, 4),
            "x3_ebit_to_assets": _round(x3, 4),
            "x4_market_equity_to_liabilities": _round(x4, 4),
            "x5_sales_to_assets": _round(x5, 4) if is_manufacturing else None,
        },
    }


def compute_dupont_analysis(
    net_income: float | None,
    operating_income: float | None,
    revenue: float | None,
    total_assets: float | None,
    stockholders_equity: float | None,
    income_tax_expense: float | None = None,
) -> dict[str, Any] | None:
    """Calculate 5-stage DuPont decomposition of Return on Equity (ROE).

    ROE = Tax Burden * Interest Burden * Operating Margin * Asset Turnover * Financial Leverage
    """
    if not revenue or revenue <= 0 or not total_assets or total_assets <= 0 or not stockholders_equity or stockholders_equity <= 0:
        return None

    ni = net_income or 0.0
    ebit = operating_income or 0.0
    tax_exp = income_tax_expense or 0.0
    ebt = ni + tax_exp if (ni and tax_exp) else ebit

    tax_burden = (ni / ebt) if (ebt and ebt > 0) else 1.0
    interest_burden = (ebt / ebit) if (ebit and ebit > 0) else 1.0
    operating_margin = (ebit / revenue)
    asset_turnover = (revenue / total_assets)
    financial_leverage = (total_assets / stockholders_equity)

    roe = (ni / stockholders_equity) if stockholders_equity else 0.0

    return {
        "roe": _round(roe, 4),
        "roe_pct": f"{round(roe * 100, 2)}%",
        "tax_burden": _round(tax_burden, 4),
        "interest_burden": _round(interest_burden, 4),
        "operating_margin": _round(operating_margin, 4),
        "asset_turnover": _round(asset_turnover, 4),
        "financial_leverage": _round(financial_leverage, 4),
        "quality_assessment": "HIGH_QUALITY_OPERATING_DRIVEN" if (operating_margin > 0.15 and asset_turnover > 0.6) else ("LEVERAGE_DRIVEN" if financial_leverage > 3.0 else "BALANCED"),
    }


def compute_roic_economic_spread(
    operating_income: float | None,
    total_assets: float | None,
    cash_and_equivalents: float | None,
    current_liabilities: float | None,
    effective_tax_rate: float = 0.21,
    wacc: float = 0.09,
) -> dict[str, Any] | None:
    """Calculate Return on Invested Capital (ROIC) and EVA Economic Value Added Spread.

    Invested Capital = Total Assets - Excess Cash - Non-Interest Bearing Current Liabilities
    NOPAT = EBIT * (1 - t)
    ROIC = NOPAT / Invested Capital
    EVA Spread = ROIC - WACC
    """
    if operating_income is None or not total_assets or total_assets <= 0:
        return None

    nopat = operating_income * (1.0 - effective_tax_rate)
    cash = cash_and_equivalents or 0.0
    cl = current_liabilities or 0.0
    invested_capital = max(total_assets - cash - cl, 1.0)
    roic = nopat / invested_capital
    spread = roic - wacc

    return {
        "nopat": _round(nopat, 2),
        "invested_capital": _round(invested_capital, 2),
        "roic": _round(roic, 4),
        "roic_pct": f"{round(roic * 100, 2)}%",
        "wacc": _round(wacc, 4),
        "wacc_pct": f"{round(wacc * 100, 2)}%",
        "economic_value_spread": _round(spread, 4),
        "economic_spread_pct": f"{round(spread * 100, 2)}%",
        "value_creation_status": "VALUE_CREATING" if spread > 0.02 else ("VALUE_NEUTRAL" if spread >= -0.02 else "VALUE_DESTROYING"),
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
    rev_curr = _val("revenue", curr_p)
    rev_prev = _val("revenue", prev_p)
    gm_curr = _val("gross_margin_pct", curr_p)
    gm_prev = _val("gross_margin_pct", prev_p)

    # 4a. SGI (Sales Growth Index)
    sgi = (rev_curr / rev_prev) if (rev_curr and rev_prev and rev_prev > 0) else 1.0

    # 4b. GMI (Gross Margin Index)
    gmi = (gm_prev / gm_curr) if (gm_prev and gm_curr and gm_curr > 0) else 1.0

    # 4c. DSRI (Days Sales in Receivables Index)
    ar_curr = _val("accounts_receivable", curr_p)
    ar_prev = _val("accounts_receivable", prev_p)
    if ar_curr is not None and ar_prev and ar_prev > 0 and rev_curr and rev_prev and rev_curr > 0 and rev_prev > 0:
        dsri = (ar_curr / rev_curr) / (ar_prev / rev_prev)
    else:
        dsri = 1.0

    # 4d. AQI (Asset Quality Index)
    ca_curr = _val("current_assets", curr_p)
    ca_prev = _val("current_assets", prev_p)
    ppe_curr = _val("ppe", curr_p)
    ppe_prev = _val("ppe", prev_p)
    if (
        ca_curr is not None and ppe_curr is not None and total_assets and total_assets > 0
        and ca_prev is not None and ppe_prev is not None and prev_assets and prev_assets > 0
    ):
        non_ca_curr = 1.0 - ((ca_curr + ppe_curr) / total_assets)
        non_ca_prev = 1.0 - ((ca_prev + ppe_prev) / prev_assets)
        aqi = (non_ca_curr / non_ca_prev) if non_ca_prev and non_ca_prev > 0 else 1.0
    else:
        aqi = 1.0

    # 4e. DEPI (Depreciation Index)
    depr_curr = _val("depreciation", curr_p)
    depr_prev = _val("depreciation", prev_p)
    if (
        depr_curr is not None and ppe_curr is not None and (ppe_curr + depr_curr) > 0
        and depr_prev is not None and ppe_prev is not None and (ppe_prev + depr_prev) > 0
    ):
        depr_rate_curr = depr_curr / (ppe_curr + depr_curr)
        depr_rate_prev = depr_prev / (ppe_prev + depr_prev)
        depi = (depr_rate_prev / depr_rate_curr) if depr_rate_curr and depr_rate_curr > 0 else 1.0
    else:
        depi = 1.0

    # 4f. SGAI (Sales, General and Administrative expenses Index)
    sga_curr = _val("sg_and_a", curr_p)
    sga_prev = _val("sg_and_a", prev_p)
    if sga_curr is not None and sga_prev and sga_prev > 0 and rev_curr and rev_prev and rev_curr > 0 and rev_prev > 0:
        sgai = (sga_curr / rev_curr) / (sga_prev / rev_prev)
    else:
        sgai = 1.0

    # 4g. LVGI (Leverage Index)
    cl_curr = _val("current_liabilities", curr_p) or 0.0
    cl_prev = _val("current_liabilities", prev_p) or 0.0
    debt_prev = _val("total_debt", prev_p)
    if total_assets and total_assets > 0 and prev_assets and prev_assets > 0:
        lev_curr = (cl_curr + (total_debt or 0.0)) / total_assets
        lev_prev = (cl_prev + (debt_prev or 0.0)) / prev_assets
        lvgi = (lev_curr / lev_prev) if lev_prev and lev_prev > 0 else 1.0
    else:
        lvgi = 1.0

    # 4h. TATA (Total Accruals to Total Assets)
    tata = ((op_inc - cfo) / total_assets) if (op_inc is not None and cfo is not None and total_assets and total_assets > 0) else 0.0

    beneish = compute_beneish_m_score(
        dsri=dsri,
        gmi=gmi,
        aqi=aqi,
        sgi=sgi,
        depi=depi,
        sgai=sgai,
        tata=tata,
        lvgi=lvgi,
    )

    # 5. Altman Z-Score, DuPont 5-Stage ROE, and ROIC/EVA Spread
    retained_earnings = _val("retained_earnings", curr_p)
    stockholders_equity = _val("stockholders_equity", curr_p)
    tax_exp = _val("income_tax_expense", curr_p)
    working_capital = (ca_curr - cl_curr) if (ca_curr is not None and cl_curr is not None) else None
    tot_liab = (total_assets - stockholders_equity) if (total_assets and stockholders_equity) else (cl_curr + (total_debt or 0.0))

    altman = compute_altman_z_score(
        working_capital=working_capital,
        retained_earnings=retained_earnings,
        ebit=op_inc,
        market_cap=None,
        total_liabilities=tot_liab,
        sales=rev_curr,
        total_assets=total_assets,
        is_manufacturing=True,
    )

    dupont = compute_dupont_analysis(
        net_income=net_income,
        operating_income=op_inc,
        revenue=rev_curr,
        total_assets=total_assets,
        stockholders_equity=stockholders_equity,
        income_tax_expense=tax_exp,
    )

    economic_spread = compute_roic_economic_spread(
        operating_income=op_inc,
        total_assets=total_assets,
        cash_and_equivalents=cash,
        current_liabilities=cl_curr,
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
    if altman and altman.get("distress_risk") == "HIGH":
        red_flags.append(f"Altman Z-Score in distress zone ({altman.get('z_score')} < 1.81)")

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
        "altman_z_score": altman,
        "dupont_analysis": dupont,
        "economic_value_spread": economic_spread,
        "working_capital": {
            "dio": _val("dio", curr_p),
            "dso": _val("dso", curr_p),
            "dpo": _val("dpo", curr_p),
            "ccc": _val("ccc", curr_p),
        },
        "red_flags": red_flags,
        "missing_inputs": missing,
    }
