"""Tool registry wrapping all 8 normalized research tools for LangGraph.

Provides duplicate call suppression and exception shielding.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence
from langchain_core.tools import BaseTool, tool

from app.social.search import search_social as _search_social
from app.articles.search import search_articles as _search_articles
from app.articles.reader import read_article as _read_article
from app.websearch.search import search_web as _search_web
from app.market.market_data import get_market_data as _get_market_data
from app.market.company_research import get_company_research as _get_company_research
from app.sec.acquisition import list_sec_filings as _list_sec_filings
from app.sec.pull import pull_sec_filings as _pull_sec_filings, SelectedSecDocument
from app.sec.verifier import verify_sec_claim as _verify_sec_claim
from app.sec.financials import get_sec_financials as _get_sec_financials


@dataclass
class ToolCallGuard:
    """Detects and suppresses repeated identical tool calls."""

    max_identical: int = 2
    _counts: dict[tuple[str, Any], int] = field(default_factory=dict)

    def check_and_record(self, signature: tuple[str, Any]) -> bool:
        """Record signature and return True if duplicate limit exceeded."""
        current = self._counts.get(signature, 0)
        if current >= self.max_identical:
            return True
        self._counts[signature] = current + 1
        return False


def create_agent_tools(
    cases_root: Path | str | None = None,
    guard: ToolCallGuard | None = None,
) -> list[BaseTool]:
    """Create all 8 normalized tools bound to LangChain BaseTool interfaces."""
    call_guard = guard or ToolCallGuard()
    root_path = Path(cases_root) if cases_root else Path("cases")

    def _guard_check(tool_name: str, kwargs: dict[str, Any]) -> str | None:
        # Freeze kwargs into a hashable signature
        items = tuple(sorted((k, str(v)) for k, v in kwargs.items()))
        sig = (tool_name, items)
        if call_guard.check_and_record(sig):
            return json.dumps({
                "status": "duplicate_suppressed",
                "message": f"Identical {tool_name} call already performed. Use prior evidence.",
            })
        return None

    @tool
    def search_social(query: str | None = None, ticker: str | None = None, time_window: str | None = None) -> str:
        """Search social media (Reddit, ApeWisdom) for sentiment, volume velocity, and hype spikes."""
        suppressed = _guard_check("search_social", {"query": query, "ticker": ticker, "time_window": time_window})
        if suppressed:
            return suppressed
        try:
            res = _search_social(query=query, ticker=ticker, time_window=time_window)
            return json.dumps(res.to_dict())
        except Exception as exc:
            return json.dumps({"status": "error", "message": f"search_social error: {exc}"})

    @tool
    def search_articles(query: str, ticker: str | None = None, sources: list[str] | None = None, days: int = 7, limit: int = 20) -> str:
        """Search professional financial news and analysis via GDELT and curated RSS feeds."""
        suppressed = _guard_check("search_articles", {"query": query, "ticker": ticker, "days": days})
        if suppressed:
            return suppressed
        try:
            res = _search_articles(query=query, ticker=ticker, sources=sources, days=days, limit=limit)
            return json.dumps(res.to_dict())
        except Exception as exc:
            return json.dumps({"status": "error", "message": f"search_articles error: {exc}"})

    @tool
    def read_article(url: str) -> str:
        """Extract cleaned text from a professional article URL. Paywall-safe; never bypasses walls."""
        suppressed = _guard_check("read_article", {"url": url})
        if suppressed:
            return suppressed
        try:
            res = _read_article(url=url)
            return json.dumps(res.to_dict())
        except Exception as exc:
            return json.dumps({"status": "error", "message": f"read_article error: {exc}"})

    @tool
    def search_web(query: str, domains: list[str] | None = None, limit: int = 10) -> str:
        """Search general web for company, counterparty, IR, press release, and regulatory sources."""
        suppressed = _guard_check("search_web", {"query": query, "domains": str(domains)})
        if suppressed:
            return suppressed
        try:
            res = _search_web(query=query, domains=domains, limit=limit)
            return json.dumps(res.to_dict())
        except Exception as exc:
            return json.dumps({"status": "error", "message": f"search_web error: {exc}"})

    @tool
    def get_market_data(ticker: str, period: str | None = None, benchmark_ticker: str = "SPY") -> str:
        """Get compact market context (returns 1d/5d/1m/3m, volume ratio, 50/200 SMA, ATR). Never signals."""
        suppressed = _guard_check("get_market_data", {"ticker": ticker, "period": period})
        if suppressed:
            return suppressed
        try:
            res = _get_market_data(ticker=ticker, period=period, benchmark_ticker=benchmark_ticker)
            return json.dumps(res.to_dict())
        except Exception as exc:
            return json.dumps({"status": "error", "message": f"get_market_data error: {exc}"})

    @tool
    def get_company_research(ticker: str) -> str:
        """Fetch Wall Street consensus data (price targets, ratings, EPS/revenue estimates, earnings date) for the expectation-gap comparison. Secondary data, never a recommendation."""
        suppressed = _guard_check("get_company_research", {"ticker": ticker})
        if suppressed:
            return suppressed
        try:
            res = _get_company_research(ticker=ticker)
            return json.dumps(res.to_dict())
        except Exception as exc:
            return json.dumps({"status": "error", "message": f"get_company_research error: {exc}"})

    @tool
    def list_sec_filings(ticker: str, forms: list[str] | None = None, since: str | None = None) -> str:
        """List metadata-only official SEC EDGAR filings for a ticker (8-K, 10-K, 10-Q, S-1, Form 4)."""
        suppressed = _guard_check("list_sec_filings", {"ticker": ticker, "forms": str(forms), "since": since})
        if suppressed:
            return suppressed
        try:
            res = _list_sec_filings(ticker=ticker, forms=forms, since=since)
            if res.error:
                return json.dumps({"status": "error", "code": res.error.code, "message": res.error.message})
            return json.dumps({"status": "ok", "filings": [f.to_dict() for f in res.filings]})
        except Exception as exc:
            return json.dumps({"status": "error", "message": f"list_sec_filings error: {exc}"})

    @tool
    def pull_sec_filings(case_id: str, selections: list[dict[str, Any]]) -> str:
        """Download explicitly selected SEC documents and exhibits into the case-local corpus."""
        suppressed = _guard_check("pull_sec_filings", {"case_id": case_id, "selections": str(selections)})
        if suppressed:
            return suppressed
        try:
            selected_docs = [
                SelectedSecDocument(
                    accession=s["accession"],
                    form=s["form"],
                    filing_date=s["filing_date"],
                    document_name=s["document_name"],
                    source_url=s["source_url"],
                )
                for s in selections
            ]
            res = _pull_sec_filings(cases_root=root_path, case_id=case_id, selections=selected_docs)
            if res.error:
                return json.dumps({"status": "error", "code": res.error.code, "message": res.error.message})
            return json.dumps({"status": "ok", "corpus": res.corpus.to_dict() if res.corpus else None})
        except Exception as exc:
            return json.dumps({"status": "error", "message": f"pull_sec_filings error: {exc}"})

    @tool
    def verify_sec_claim(corpus_id: str, claim: str) -> str:
        """Verify a specific factual claim against local SEC corpus documents. Returns CONFIRMED/CONTRADICTED."""
        suppressed = _guard_check("verify_sec_claim", {"corpus_id": corpus_id, "claim": claim})
        if suppressed:
            return suppressed
        try:
            case_dir = root_path / corpus_id
            res = _verify_sec_claim(case_directory=case_dir, claim=claim)
            if res.error:
                return json.dumps({"status": "error", "code": res.error.code, "message": res.error.message})
            return json.dumps({"status": "ok", "verification": res.verification.to_dict() if res.verification else None})
        except Exception as exc:
            return json.dumps({"status": "error", "message": f"verify_sec_claim error: {exc}"})

    @tool
    def get_sec_financials(ticker: str, periods: int = 4) -> str:
        """Extract official quarterly SEC XBRL metrics (gross margin %, operating margin %, net cash, inventory QoQ change, CapEx). Deterministic math with zero hallucination."""
        suppressed = _guard_check("get_sec_financials", {"ticker": ticker, "periods": periods})
        if suppressed:
            return suppressed
        try:
            res = _get_sec_financials(ticker=ticker, periods=periods)
            return json.dumps(res.to_dict())
        except Exception as exc:
            return json.dumps({"status": "error", "message": f"get_sec_financials error: {exc}"})

    return [
        search_social,
        search_articles,
        read_article,
        search_web,
        get_market_data,
        get_company_research,
        list_sec_filings,
        pull_sec_filings,
        verify_sec_claim,
        get_sec_financials,
    ]
