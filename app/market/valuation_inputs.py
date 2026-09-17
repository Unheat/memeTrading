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
