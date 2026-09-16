"""Real live end-to-end test exercising all deep research tools and the real LLM.

Uses real environment variables loaded from .env without hardcoded credentials.
Connects to actual live APIs (DuckDuckGo, yfinance, FRED, Finnhub, SEC EDGAR, and local LiteLLM model).
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

# Load real environment keys from .env
load_dotenv()

from app.agent.runner import run_investigation, InvestigationResult
from app.agent.state import ResearchRequest
from app.articles.document_reader import read_document
from app.market.company_research import get_company_research
from app.market.market_data import get_market_data
from app.market.providers.fred import get_macro_context
from app.sec.acquisition import list_sec_filings
from app.sec.financials import get_sec_financials
from app.sec.insiders import get_ownership_and_insider_activity
from app.websearch.search import search_web
from app.agent.screening import build_candidate_comparisons


def test_live_web_search_and_document_reading():
    """Verify real live web search and document reading with link harvesting."""
    # 1. Real DuckDuckGo web search
    search_res = search_web("Micron Technology investor relations news", limit=3)
    assert len(search_res.records) >= 1
    first_url = search_res.records[0].url
    assert first_url.startswith("https://")

    # 2. Real document reader fetching live HTML and harvesting document links
    doc_res = read_document(first_url)
    assert doc_res["status"] == "ok"
    assert doc_res["character_count"] > 100
    assert doc_res["content_sha256"] is not None
    assert isinstance(doc_res.get("discovered_documents"), list)


def test_live_market_and_consensus_data():
    """Verify real live stock quotes and Wall Street consensus models."""
    # 1. Real market data via yfinance
    mkt = get_market_data("MU")
    mkt_dict = mkt.to_dict()
    price = (mkt_dict.get("quote") or {}).get("price")
    assert price is not None and float(price) > 0
    assert mkt_dict.get("addv_20d", {}).get("value") is not None

    # 2. Real consensus data
    consensus = get_company_research("MU")
    c_dict = consensus.to_dict()
    ratings = c_dict.get("ratings") or {}
    assert ratings.get("total", 0) > 0
    assert (c_dict.get("price_targets") or {}).get("mean") is not None


def test_live_macro_and_insider_activity():
    """Verify real live FRED interest rates and Finnhub insider trades from .env keys."""
    # 1. Real FRED macro rates (requires FRED_API_KEY)
    fred_key = os.getenv("FRED_API_KEY")
    if fred_key:
        macro = get_macro_context(["DGS10", "FEDFUNDS"])
        assert "DGS10" in macro
        assert macro["DGS10"]["status"] == "ok"
        assert macro["DGS10"]["latest_value"] is not None

    # 2. Real insider activity (requires FINNHUB_API_KEY)
    finnhub_key = os.getenv("FINNHUB_API_KEY")
    if finnhub_key:
        insider = get_ownership_and_insider_activity("MU", limit=5)
        assert insider["status"] == "ok"
        assert insider["ticker"] == "MU"
        assert isinstance(insider["transactions"], list)


def test_live_sec_edgar_filings_and_xbrl():
    """Verify real live SEC EDGAR filing metadata discovery and XBRL financials."""
    # 1. Real SEC EDGAR filing discovery
    filings_res = list_sec_filings("MU", forms=["10-K", "10-Q"], since="2025-01-01")
    assert filings_res.error is None
    assert len(filings_res.filings) >= 1
    assert filings_res.filings[0].ticker == "MU"
    assert filings_res.filings[0].accession is not None

    # 2. Real SEC XBRL financials
    sec_fin = get_sec_financials("MU", periods=2)
    assert sec_fin.status == "ok"
    assert len(sec_fin.periods) >= 1
    latest_p = sec_fin.periods[0]
    assert latest_p in sec_fin.gross_margin_pct


def test_candidate_comparisons_logic():
    """Verify multi-candidate normalization across multiple tickers."""
    candidates = {
        "cand_mu": {
            "ticker": "MU",
            "market_context": {"quote": {"price": 100.0}, "fundamentals": {"pe_ratio": 20.0}},
            "sec_financials": {"periods": ["2026-Q2"], "gross_margin_pct": {"2026-Q2": 0.35}},
        },
        "cand_nvda": {
            "ticker": "NVDA",
            "market_context": {"quote": {"price": 120.0}, "fundamentals": {"pe_ratio": 45.0}},
            "sec_financials": {"periods": ["2026-Q2"], "gross_margin_pct": {"2026-Q2": 0.75}},
        },
    }
    cards = build_candidate_comparisons(candidates, ["cand_mu", "cand_nvda"], metrics=["price", "gross_margin"])
    assert len(cards) == 2
    assert "MU" in cards[0]["candidate_values"]
    assert "NVDA" in cards[0]["candidate_values"]


def test_live_end_to_end_investigation_with_real_model(tmp_path: Path):
    """Execute a real end-to-end investigation with the live LLM through LiteLLM.

    The model reads the research request, chooses and calls real tools, gathers real data,
    and produces an audited case folder with investigation.json and memo.md.
    """
    req = ResearchRequest(
        query="Analyze Micron DDR5 and HBM3E memory demand catalysts",
        ticker="MU",
        company="Micron Technology Inc",
    )
    result = run_investigation(
        request=req,
        cases_root=tmp_path,
        generate_media=False,
    )

    assert isinstance(result, InvestigationResult)
    assert result.ticker == "MU"
    assert result.status in ("completed", "research_incomplete")
    assert result.memo_markdown is not None
    assert len(result.memo_markdown) > 100

    # Verify real disk artifacts created in case directory
    case_dir = tmp_path / result.case_id
    assert case_dir.exists()
    assert (case_dir / "investigation.json").exists()
    assert (case_dir / "memo.md").exists()
    assert (case_dir / "run-manifest.json").exists()

    # Verify real tool receipts were logged
    receipts = result.final_state.get("searches_performed", [])
    assert len(receipts) >= 1
    assert any(r.get("status") == "ok" for r in receipts)
