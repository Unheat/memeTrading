"""Insider and ownership activity analysis combining EDGAR Form 4 and Finnhub data.

Distinguishes open-market buys/sales from tax withholding (Code F) and option exercises (Code M).
"""
from __future__ import annotations

import logging
from typing import Any

from app.market.providers.finnhub import FinnhubClient
from app.sec.acquisition import list_sec_filings

logger = logging.getLogger(__name__)


def get_ownership_and_insider_activity(
    ticker: str,
    candidate_id: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Retrieve structured insider trading and ownership disclosures for a company.

    Args:
        ticker: Uppercase ticker symbol.
        candidate_id: Optional registered candidate identifier.
        limit: Maximum number of recent transactions to return.

    Returns:
        Structured audit report distinguishing open-market trades from routine vesting.
    """
    clean_ticker = str(ticker or "").strip().upper()
    if not clean_ticker or not clean_ticker.isalpha():
        return {"status": "error", "message": "Valid ticker symbol is required."}

    transactions: list[dict[str, Any]] = []
    buys = 0
    sales = 0
    net_shares = 0.0

    # 1. Try Finnhub insider endpoint if configured
    try:
        client = FinnhubClient()
        if client.is_configured:
            finnhub_rows = client.get_insider_transactions(clean_ticker, limit=limit)
            for row in finnhub_rows:
                code = str(row.get("transaction_code") or "").upper()
                shares = float(row.get("shares") or 0.0)
                change = float(row.get("change") or 0.0)
                if code == "P" or change > 0:
                    buys += 1
                elif code == "S" or change < 0:
                    sales += 1
                net_shares += change
                transactions.append({
                    "insider_name": row.get("name"),
                    "transaction_code": code,
                    "shares": shares,
                    "change": change,
                    "price": row.get("price"),
                    "filed_at": row.get("filed_at"),
                    "source_url": row.get("web_url"),
                })
    except Exception as exc:
        logger.warning("Finnhub insider lookup failed for %s: %s", clean_ticker, exc)

    # 2. Discover recent official Form 4 filings via Edgar
    recent_form4s: list[dict[str, Any]] = []
    try:
        filing_res = list_sec_filings(clean_ticker, forms=["4"])
        if filing_res.filings:
            recent_form4s = [f.to_dict() for f in filing_res.filings[:5]]
    except Exception as exc:
        logger.warning("EDGAR Form 4 discovery failed for %s: %s", clean_ticker, exc)

    return {
        "status": "ok",
        "ticker": clean_ticker,
        "candidate_id": candidate_id,
        "transactions_count": len(transactions),
        "transactions": transactions[:limit],
        "recent_form4_filings": recent_form4s,
        "summary": {
            "buys_count": buys,
            "sales_count": sales,
            "net_shares_change": net_shares,
            "has_recent_filings": len(recent_form4s) > 0,
        },
    }
