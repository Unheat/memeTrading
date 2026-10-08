"""Verified market-input normalization for deterministic valuation.

This module accepts only finite, source-provided price and share observations. It never
estimates missing market inputs and records whether a valuation uses a live price or
an observed prior close.
"""
from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any


def _finite_positive(value: Any) -> float | None:
    """Return a finite positive numeric value or ``None``."""
    if isinstance(value, bool):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) and numeric > 0 else None


def resolve_valuation_market_inputs(market_context: Mapping[str, Any] | None) -> dict[str, Any]:
    """Resolve verified price and diluted shares from a market context payload.

    Args:
        market_context: Provider-normalized market result with quote and fundamentals.

    Returns:
        Dictionary with price, shares, deterministic provenance, and named missing inputs.
    """
    market = market_context if isinstance(market_context, Mapping) else {}
    quote = market.get("quote") if isinstance(market.get("quote"), Mapping) else {}
    fundamentals = market.get("fundamentals") if isinstance(market.get("fundamentals"), Mapping) else {}

    live_price = _finite_positive(quote.get("price"))
    prior_close = _finite_positive(quote.get("previous_close"))
    if live_price is not None:
        price = live_price
        input_field = "market_context.quote.price"
        price_basis = "latest_quote"
        fallback_used = False
    elif prior_close is not None:
        price = prior_close
        input_field = "market_context.quote.previous_close"
        price_basis = "prior_close"
        fallback_used = True
    else:
        price = None
        input_field = None
        price_basis = None
        fallback_used = False

    raw_shares = fundamentals.get("shares_outstanding")
    if isinstance(raw_shares, Mapping):
        shares = _finite_positive(raw_shares.get("value")) if raw_shares.get("reliable") is True else None
        shares_path = "market_context.fundamentals.shares_outstanding.value"
    else:
        shares = _finite_positive(raw_shares)
        shares_path = "market_context.fundamentals.shares_outstanding"

    missing_inputs = []
    if price is None:
        missing_inputs.append("verified market price or prior close")
    if shares is None:
        missing_inputs.append("reliable diluted shares outstanding")

    return {
        "price": price,
        "shares_outstanding": shares,
        "missing_inputs": missing_inputs,
        "provenance": {
            "price_input_field": input_field,
            "price_basis": price_basis,
            "fallback_used": fallback_used,
            "shares_input_field": shares_path,
            "as_of": quote.get("as_of") or market.get("as_of"),
            "currency": quote.get("currency") or market.get("currency"),
            "exchange": quote.get("exchange") or market.get("exchange"),
        },
    }


def extract_valuation_summary(quant_report: Mapping[str, Any] | None) -> dict[str, Any]:
    """Extract a canonical valuation summary dictionary from a quant_report payload.

    Reconciles nested calculator.mjs outputs (fair_value_range, reverse_dcf, asymmetric_risk_reward)
    into a standardized valuation schema used across candidate workspaces, diligence dossiers,
    and tool returns.

    Args:
        quant_report: Output payload from run_quant_analysis or evaluate_valuation.

    Returns:
        Standardized dict with fair_value, fair_value_range, implied_growth_rate,
        reward_to_risk_ratio, and reproducibility.
    """
    quant = quant_report if isinstance(quant_report, Mapping) else {}
    val = quant.get("valuation") if isinstance(quant.get("valuation"), Mapping) else {}
    fvr = val.get("fair_value_range") if isinstance(val.get("fair_value_range"), Mapping) else {}
    rdcf = val.get("reverse_dcf") if isinstance(val.get("reverse_dcf"), Mapping) else {}
    arr = val.get("asymmetric_risk_reward") if isinstance(val.get("asymmetric_risk_reward"), Mapping) else {}
    repro = quant.get("reproducibility") if isinstance(quant.get("reproducibility"), Mapping) else {}

    fair_val = val.get("fair_value") or fvr.get("base") or fvr.get("blended_base")
    implied_g = val.get("implied_fcf_growth_rate") or val.get("implied_growth_rate") or rdcf.get("implied_fcf_growth_rate")
    ratio = val.get("reward_to_risk_ratio") or arr.get("reward_to_risk_ratio")
    repro_verdict = val.get("reproducibility") or repro.get("verdict", "unverified")

    return {
        "fair_value": float(fair_val) if fair_val is not None else None,
        "fair_value_range": {
            "low": fvr.get("low"),
            "base": fvr.get("base"),
            "high": fvr.get("high"),
            "dcf_base": fvr.get("dcf_base"),
            "blended_base": fvr.get("blended_base"),
        } if fvr else None,
        "implied_growth_rate": float(implied_g) if implied_g is not None else None,
        "reward_to_risk_ratio": float(ratio) if ratio is not None else None,
        "reproducibility": str(repro_verdict) if repro_verdict is not None else "unverified",
    }
