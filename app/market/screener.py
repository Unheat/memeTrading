"""Quantitative equity screener provider boundary.

Black-box dependency use over yfinance.screener.screener.
Provides keyless, 100% free programmatic screening over US equities
using predefined institutional screens or structured factor queries.
"""
from __future__ import annotations

import logging
from typing import Any, Mapping, Optional, Sequence

logger = logging.getLogger(__name__)

SUPPORTED_PRESETS = frozenset({
    "growth_technology_stocks",
    "undervalued_growth_stocks",
    "undervalued_large_caps",
    "most_actives",
    "day_gainers",
    "day_losers",
    "most_shorted_stocks",
    "aggressive_small_caps",
    "small_cap_gainers",
})

SECTOR_MAP = {
    "tech": "Technology",
    "technology": "Technology",
    "it": "Technology",
    "information technology": "Technology",
    "health": "Healthcare",
    "healthcare": "Healthcare",
    "financials": "Financial Services",
    "financial": "Financial Services",
    "financial services": "Financial Services",
    "banks": "Financial Services",
    "consumer cyclical": "Consumer Cyclical",
    "consumer discretionary": "Consumer Cyclical",
    "consumer defensive": "Consumer Defensive",
    "consumer staples": "Consumer Defensive",
    "industrials": "Industrials",
    "communication": "Communication Services",
    "communication services": "Communication Services",
    "energy": "Energy",
    "basic materials": "Basic Materials",
    "materials": "Basic Materials",
    "real estate": "Real Estate",
    "utilities": "Utilities",
}


SORT_FIELD_MAP = {
    "market_cap": "intradaymarketcap",
    "intradaymarketcap": "intradaymarketcap",
    "volume": "dayvolume",
    "dayvolume": "dayvolume",
    "percent_change": "percentchange",
    "percentchange": "percentchange",
    "pe_ratio": "peratio.lasttwelvemonths",
    "pe": "peratio.lasttwelvemonths",
}


def _screen_yfinance(
    query_or_preset: Any,
    count: int = 25,
    sort_field: str | None = None,
    sort_asc: bool = False,
) -> dict[str, Any]:
    """Seam over yfinance screener function to allow clean testing without live network."""
    import yfinance.screener.screener as yfs
    kwargs: dict[str, Any] = {"count": count}
    if sort_field:
        kwargs["sortField"] = sort_field
        kwargs["sortAsc"] = sort_asc
    return yfs.screen(query_or_preset, **kwargs)


def normalize_sector(sector: str | None) -> str | None:
    """Normalize user or model input sector string to standard Yahoo Finance GICS sectors.

    Args:
        sector: Raw sector string (e.g. 'tech', 'Healthcare').

    Returns:
        Canonical sector name (e.g. 'Technology', 'Healthcare'), or original title-cased if unmapped.
    """
    if not sector or not isinstance(sector, str):
        return None
    cleaned = sector.strip().lower()
    return SECTOR_MAP.get(cleaned, sector.strip().title())


def execute_equity_screen(
    preset: Optional[str] = None,
    sector: Optional[str] = None,
    min_market_cap: Optional[float] = None,
    max_market_cap: Optional[float] = None,
    max_pe_ratio: Optional[float] = None,
    min_revenue_growth_pct: Optional[float] = None,
    sort_by: Optional[str] = "market_cap",
    sort_asc: bool = False,
    limit: int = 25,
) -> dict[str, Any]:
    """Execute quantitative equity screener across US major exchanges.

    Args:
        preset: Optional predefined Wall Street screen name (e.g. 'growth_technology_stocks').
        sector: Optional sector filter (e.g. 'Technology', 'Healthcare').
        min_market_cap: Minimum intraday market capitalization in USD.
        max_market_cap: Maximum intraday market capitalization in USD.
        max_pe_ratio: Maximum trailing P/E ratio.
        min_revenue_growth_pct: Minimum quarterly revenue growth percentage.
        sort_by: Criterion to sort results ('market_cap', 'volume', 'percent_change', 'pe_ratio').
        sort_asc: True for ascending sort, False for descending (defaults to False, highest first).
        limit: Maximum number of candidate results to return (1-25, default 25).

    Returns:
        Structured dictionary containing status, match count, and candidate records.
    """
    safe_limit = max(1, min(25, int(limit or 25)))

    # Branch 1: Predefined screen preset
    if preset and str(preset).strip().lower() in SUPPORTED_PRESETS:
        clean_preset = str(preset).strip().lower()
        try:
            raw_response = _screen_yfinance(clean_preset, count=safe_limit)
            quotes = raw_response.get("quotes", [])
            records = _format_quotes(quotes, safe_limit)
            return {
                "status": "ok",
                "count": len(records),
                "preset": clean_preset,
                "records": records,
            }
        except Exception as exc:
            logger.warning("Preset equity screen '%s' failed: %s", clean_preset, exc)
            return {"status": "error", "message": f"screener failed: {exc}", "records": []}

    # Branch 2: Structured custom criteria query
    try:
        import yfinance.screener.screener as yfs
        from yfinance.screener.screener import EqyQy

        subqueries = [
            EqyQy("is-in", ["exchange", "NMS", "NYQ"]),
        ]

        norm_sec = normalize_sector(sector)
        if norm_sec:
            subqueries.append(EqyQy("eq", ["sector", norm_sec]))

        if min_market_cap is not None and float(min_market_cap) > 0:
            subqueries.append(EqyQy("gte", ["intradaymarketcap", float(min_market_cap)]))

        if max_market_cap is not None and float(max_market_cap) > 0:
            subqueries.append(EqyQy("lte", ["intradaymarketcap", float(max_market_cap)]))

        if max_pe_ratio is not None and float(max_pe_ratio) > 0:
            subqueries.append(EqyQy("btwn", ["peratio.lasttwelvemonths", 0, float(max_pe_ratio)]))

        if min_revenue_growth_pct is not None:
            subqueries.append(EqyQy("gte", ["quarterlyrevenuegrowth.quarterly", float(min_revenue_growth_pct)]))

        sort_field = SORT_FIELD_MAP.get(str(sort_by).strip().lower(), "intradaymarketcap") if sort_by else "intradaymarketcap"

        if len(subqueries) == 1 and not norm_sec:
            # If no filters provided, default to growth tech preset
            raw_response = _screen_yfinance("growth_technology_stocks", count=safe_limit)
        else:
            query = EqyQy("and", subqueries)
            raw_response = _screen_yfinance(query, count=safe_limit, sort_field=sort_field, sort_asc=sort_asc)

        quotes = raw_response.get("quotes", [])
        records = _format_quotes(quotes, safe_limit)
        return {
            "status": "ok",
            "count": len(records),
            "sector": norm_sec,
            "sorted_by": sort_field,
            "records": records,
        }
    except Exception as exc:
        logger.warning("Custom equity screen failed: %s", exc)
        return {"status": "error", "message": f"screener failed: {exc}", "records": []}


def _format_quotes(quotes: Sequence[Mapping[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Format and normalize raw yfinance quotes into clean financial candidate dictionaries."""
    formatted = []
    for q in quotes[:limit]:
        if not isinstance(q, Mapping):
            continue
        ticker = str(q.get("symbol") or "").strip().upper()
        if not ticker:
            continue
        name = str(q.get("shortName") or q.get("longName") or ticker).strip()
        price = q.get("regularMarketPrice") or q.get("fulldayPrice")
        mcap = q.get("marketCap")
        pe = q.get("trailingPE")
        fwd_pe = q.get("forwardPE")
        rating = q.get("averageAnalystRating")
        exchange = q.get("fullExchangeName") or q.get("exchange") or "US"

        summary_parts = [f"{name} ({ticker}) on {exchange}"]
        if price is not None:
            summary_parts.append(f"Price: ${float(price):.2f}")
        if mcap is not None:
            cap_billions = float(mcap) / 1e9
            summary_parts.append(f"Market Cap: ${cap_billions:.1f}B")
        if pe is not None:
            summary_parts.append(f"Trailing P/E: {float(pe):.1f}")
        if rating:
            summary_parts.append(f"Consensus: {rating}")

        formatted.append({
            "ticker": ticker,
            "company": name,
            "price": float(price) if price is not None else None,
            "market_cap": float(mcap) if mcap is not None else None,
            "trailing_pe": float(pe) if pe is not None else None,
            "forward_pe": float(fwd_pe) if fwd_pe is not None else None,
            "analyst_rating": str(rating) if rating else None,
            "exchange": str(exchange),
            "summary": "; ".join(summary_parts),
        })
    return formatted
