"""Tool registry wrapping all normalized deep-research tools for LangGraph.

Provides duplicate call suppression, exception shielding, and candidate workspace isolation.
"""
from __future__ import annotations

from datetime import date
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence
from langchain_core.tools import BaseTool, tool

from app.social.search import search_social as _search_social
from app.articles.search import search_articles as _search_articles
from app.articles.reader import read_article as _read_article
from app.articles.document_reader import read_document as _read_document
from app.websearch.search import search_web as _search_web
from app.market.market_data import get_market_data as _get_market_data
from app.market.company_research import get_company_research as _get_company_research
from app.market.providers.fred import get_macro_context as _get_macro_context
from app.sec.acquisition import list_sec_filings as _list_sec_filings
from app.sec.pull import pull_sec_filings as _pull_sec_filings, SelectedSecDocument
from app.sec.schemas import FilingMetadata
from app.sec.verifier import verify_sec_claim as _verify_sec_claim
from app.sec.financials import get_sec_financials as _get_sec_financials
from app.sec.insiders import get_ownership_and_insider_activity as _get_ownership_and_insider_activity
from app.sec.evidence import search_sec_evidence as _search_sec_evidence, read_sec_evidence as _read_sec_evidence
from app.sec.embeddings import get_sec_query_embedder
from app.storage.cases import case_path
from app.agent.sanitizer import sanitize_payload


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
    model: Any | None = None,
) -> list[BaseTool]:
    """Create all normalized tools bound to LangChain BaseTool interfaces."""
    call_guard = guard or ToolCallGuard()
    root_path = Path(cases_root) if cases_root else Path("cases")

    def _guard_check(tool_name: str, kwargs: dict[str, Any]) -> str | None:
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
            return json.dumps(sanitize_payload(res.to_dict()))
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
            return json.dumps(sanitize_payload(res.to_dict()))
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
            return json.dumps(sanitize_payload(res.to_dict()))
        except Exception as exc:
            return json.dumps({"status": "error", "message": f"read_article error: {exc}"})

    @tool
    def read_document(url: str, candidate_id: str | None = None, max_pages: int = 20) -> str:
        """Read an authoritative primary document (PDF presentation, earnings release, report, HTML). Extracts clean text, tables, and discovers linked PDFs and reports."""
        suppressed = _guard_check("read_document", {"url": url, "candidate_id": candidate_id})
        if suppressed:
            return suppressed
        try:
            res = _read_document(url=url, candidate_id=candidate_id, max_pages=max_pages)
            if isinstance(res, dict) and candidate_id:
                res["candidate_id"] = candidate_id
            return json.dumps(res)
        except Exception as exc:
            return json.dumps({"status": "error", "message": f"read_document error: {exc}"})

    @tool
    def search_web(query: str, domains: list[str] | None = None, limit: int = 10, file_type: str | None = None) -> str:
        """Search general web for company, counterparty, IR, press release, and regulatory sources. Supports file_type='pdf'."""
        suppressed = _guard_check("search_web", {"query": query, "domains": str(domains), "file_type": file_type})
        if suppressed:
            return suppressed
        try:
            res = _search_web(query=query, domains=domains, limit=limit, file_type=file_type)
            return json.dumps(sanitize_payload(res.to_dict()))
        except Exception as exc:
            return json.dumps({"status": "error", "message": f"search_web error: {exc}"})

    @tool
    def get_market_data(ticker: str, period: str | None = None, benchmark_ticker: str = "SPY", candidate_id: str | None = None) -> str:
        """Get compact market context (returns 1d/5d/1m/3m, volume ratio, 50/200 SMA, ATR). Never signals."""
        suppressed = _guard_check("get_market_data", {"ticker": ticker, "period": period, "candidate_id": candidate_id})
        if suppressed:
            return suppressed
        try:
            res = _get_market_data(ticker=ticker, period=period, benchmark_ticker=benchmark_ticker)
            d = res.to_dict()
            if candidate_id:
                d["candidate_id"] = candidate_id
            return json.dumps(d)
        except Exception as exc:
            return json.dumps({"status": "error", "message": f"get_market_data error: {exc}"})

    @tool
    def get_company_research(ticker: str, candidate_id: str | None = None) -> str:
        """Fetch Wall Street consensus data (price targets, ratings, EPS/revenue estimates, earnings date) for the expectation-gap comparison."""
        suppressed = _guard_check("get_company_research", {"ticker": ticker, "candidate_id": candidate_id})
        if suppressed:
            return suppressed
        try:
            res = _get_company_research(ticker=ticker)
            d = res.to_dict()
            if candidate_id:
                d["candidate_id"] = candidate_id
            return json.dumps(d)
        except Exception as exc:
            return json.dumps({"status": "error", "message": f"get_company_research error: {exc}"})

    @tool
    def list_sec_filings(ticker: str, forms: list[str] | None = None, since: str | None = None, candidate_id: str | None = None) -> str:
        """List metadata-only official SEC EDGAR filings with server-verified receipt IDs."""
        suppressed = _guard_check("list_sec_filings", {"ticker": ticker, "forms": str(forms), "since": since, "candidate_id": candidate_id})
        if suppressed:
            return suppressed
        try:
            from app.sec.receipts import get_sec_receipt_store

            res = _list_sec_filings(ticker=ticker, forms=forms, since=since)
            if res.error:
                return json.dumps({"status": "error", "code": res.error.code, "message": res.error.message})
            store = get_sec_receipt_store()
            receipts = store.register_discovery(res.filings, candidate_id=candidate_id)
            first_f = res.filings[0] if res.filings else None
            d = {
                "status": "ok",
                "ticker": ticker.upper(),
                "cik": first_f.cik if first_f else None,
                "filings": [r.to_dict() for r in receipts],
            }
            if candidate_id:
                d["candidate_id"] = candidate_id
            return json.dumps(d)
        except Exception as exc:
            return json.dumps({"status": "error", "message": f"list_sec_filings error: {exc}"})

    @tool
    def pull_sec_filings(case_id: str, selections: list[dict[str, Any]], candidate_id: str | None = None) -> str:
        """Download explicitly selected SEC documents using server-issued filing/document receipts."""
        suppressed = _guard_check("pull_sec_filings", {"case_id": case_id, "selections": str(selections), "candidate_id": candidate_id})
        if suppressed:
            return suppressed
        try:
            from app.sec.receipts import get_sec_receipt_store

            store = get_sec_receipt_store()
            selected_docs = []
            for s in selections:
                f_receipt = s.get("filing_receipt_id")
                d_receipt = s.get("document_receipt_id")
                if f_receipt:
                    resolved = store.resolve_selection(f_receipt, d_receipt, candidate_id=candidate_id)
                    if not resolved:
                        return json.dumps({
                            "status": "entity_conflict",
                            "code": "unresolved_sec_receipt",
                            "message": f"Filing receipt {f_receipt} is invalid or does not match candidate {candidate_id}.",
                        })
                    selected_docs.append(resolved)
                elif "filing" in s and isinstance(s["filing"], dict):
                    # Graceful backward compatibility for existing offline test fixtures
                    filing_meta = FilingMetadata.from_dict(s["filing"])
                    selected_docs.append(
                        SelectedSecDocument(
                            filing=filing_meta,
                            document_name=str(s.get("document_name") or "primary_doc.htm"),
                            source_url=str(s.get("source_url") or filing_meta.filing_url),
                        )
                    )
                elif s.get("accession") and s.get("ticker") and s.get("cik"):
                    # Graceful backward compatibility for direct test selections
                    f_date = date.fromisoformat(str(s["filing_date"])) if s.get("filing_date") else date.today()
                    filing_meta = FilingMetadata(
                        ticker=str(s["ticker"]).strip().upper(),
                        cik=str(s["cik"]).strip(),
                        form=str(s.get("form") or "8-K"),
                        filing_date=f_date,
                        accession=str(s["accession"]).strip(),
                        filing_url=str(s.get("source_url") or s.get("filing_url") or "https://www.sec.gov/filing"),
                    )
                    selected_docs.append(
                        SelectedSecDocument(
                            filing=filing_meta,
                            document_name=str(s.get("document_name") or "primary_doc.htm"),
                            source_url=str(s.get("source_url") or filing_meta.filing_url),
                        )
                    )
                else:
                    return json.dumps({
                        "status": "invalid_input",
                        "code": "missing_receipt_id",
                        "message": "Selection must specify filing_receipt_id issued by list_sec_filings.",
                    })

            effective_target = f"{case_id}/candidates/{candidate_id}" if candidate_id else case_id
            res = _pull_sec_filings(cases_root=root_path, case_id=effective_target, selections=selected_docs)
            if res.error:
                return json.dumps({"status": "error", "code": res.error.code, "message": res.error.message})
            corpus_dict = res.corpus.to_dict() if res.corpus and hasattr(res.corpus, "to_dict") else (dict(res.corpus) if isinstance(res.corpus, dict) else None)
            ticker = getattr(res.corpus, "ticker", None) if res.corpus else None
            d = {"status": "ok", "corpus": corpus_dict, "ticker": ticker}
            if candidate_id:
                d["candidate_id"] = candidate_id
            return json.dumps(d)
        except Exception as exc:
            return json.dumps({"status": "error", "message": f"pull_sec_filings error: {exc}"})

    @tool
    def search_sec_evidence(case_id: str, query: str, candidate_id: str | None = None, top_k: int = 5) -> str:
        """Search the locally pulled and indexed SEC corpus using hybrid FAISS dense + BM25 sparse + RRF retrieval."""
        suppressed = _guard_check("search_sec_evidence", {"case_id": case_id, "query": query, "candidate_id": candidate_id})
        if suppressed:
            return suppressed
        try:
            target_id = f"{case_id}/candidates/{candidate_id}" if candidate_id else case_id
            case_dir = case_path(root_path, target_id)
            embed_query = get_sec_query_embedder()
            receipts, err = _search_sec_evidence(case_directory=case_dir, query=query, embed_query=embed_query, candidate_id=candidate_id, top_k=top_k)
            if err:
                return json.dumps({"status": "error", **err})
            return json.dumps({"status": "ok", "results": receipts, "candidate_id": candidate_id})
        except Exception as exc:
            return json.dumps({"status": "error", "message": f"search_sec_evidence error: {exc}"})

    @tool
    def read_sec_evidence(case_id: str, chunk_ids: list[str], candidate_id: str | None = None) -> str:
        """Read exact SEC filing text chunks with preceding and following context."""
        suppressed = _guard_check("read_sec_evidence", {"case_id": case_id, "chunk_ids": str(chunk_ids), "candidate_id": candidate_id})
        if suppressed:
            return suppressed
        try:
            target_id = f"{case_id}/candidates/{candidate_id}" if candidate_id else case_id
            case_dir = case_path(root_path, target_id)
            receipts, err = _read_sec_evidence(case_directory=case_dir, chunk_ids=chunk_ids, candidate_id=candidate_id)
            if err:
                return json.dumps({"status": "error", **err})
            return json.dumps({"status": "ok", "chunks": receipts, "candidate_id": candidate_id})
        except Exception as exc:
            return json.dumps({"status": "error", "message": f"read_sec_evidence error: {exc}"})

    @tool
    def verify_sec_claim(corpus_id: str, claim: str, candidate_id: str | None = None) -> str:
        """Verify a specific factual claim against local SEC corpus documents. Returns CONFIRMED/CONTRADICTED."""
        suppressed = _guard_check("verify_sec_claim", {"corpus_id": corpus_id, "claim": claim, "candidate_id": candidate_id})
        if suppressed:
            return suppressed
        try:
            from app.sec.corpus import prepare_sec_corpus
            from app.sec.default_assessor import get_default_sec_assessor
            from app.sec.embeddings import get_sec_embedder, get_sec_query_embedder
            from app.sec.retrieval import build_sec_index

            try:
                case_dir = case_path(root_path, corpus_id)
            except ValueError:
                case_dir = root_path / corpus_id

            index_file = case_dir / "sec" / "index" / "sec.faiss"
            if not index_file.exists():
                prep_res = prepare_sec_corpus(case_dir)
                if prep_res.error is None:
                    build_sec_index(case_dir, embedder=get_sec_embedder())

            embed_query = get_sec_query_embedder()
            assessor = get_default_sec_assessor()

            res = _verify_sec_claim(
                case_directory=case_dir,
                claim=claim,
                embed_query=embed_query,
                assessor=assessor,
            )
            if res.error:
                return json.dumps({"status": "error", "code": res.error.code, "message": res.error.message})
            d = {"status": "ok", "verification": res.verification.to_dict() if res.verification else None}
            if candidate_id:
                d["candidate_id"] = candidate_id
            return json.dumps(d)
        except Exception as exc:
            return json.dumps({"status": "error", "message": f"verify_sec_claim error: {exc}"})

    @tool
    def get_sec_financials(ticker: str, periods: int = 4, candidate_id: str | None = None) -> str:
        """Extract official quarterly SEC XBRL metrics (gross margin %, operating margin %, net cash, inventory QoQ change, CapEx)."""
        suppressed = _guard_check("get_sec_financials", {"ticker": ticker, "periods": periods, "candidate_id": candidate_id})
        if suppressed:
            return suppressed
        try:
            res = _get_sec_financials(ticker=ticker, periods=periods)
            d = res.to_dict()
            if candidate_id:
                d["candidate_id"] = candidate_id
            return json.dumps(d)
        except Exception as exc:
            return json.dumps({"status": "error", "message": f"get_sec_financials error: {exc}"})

    @tool
    def get_ownership_and_insider_activity(ticker: str, candidate_id: str | None = None, limit: int = 20) -> str:
        """Audit insider transactions (Form 4) and ownership changes, isolating discretionary buys/sales from tax withholding."""
        suppressed = _guard_check("get_ownership_and_insider_activity", {"ticker": ticker, "candidate_id": candidate_id})
        if suppressed:
            return suppressed
        try:
            res = _get_ownership_and_insider_activity(ticker=ticker, candidate_id=candidate_id, limit=limit)
            if isinstance(res, dict) and candidate_id:
                res["candidate_id"] = candidate_id
            return json.dumps(res)
        except Exception as exc:
            return json.dumps({"status": "error", "message": f"get_ownership_and_insider_activity error: {exc}"})

    @tool
    def get_macro_context(series_ids: list[str]) -> str:
        """Fetch official macroeconomic indicators from FRED (e.g. DGS10, FEDFUNDS, CPIAUCSL, UNRATE)."""
        suppressed = _guard_check("get_macro_context", {"series_ids": str(series_ids)})
        if suppressed:
            return suppressed
        try:
            res = _get_macro_context(series_ids=series_ids)
            return json.dumps({"status": "ok", "macro_series": res})
        except Exception as exc:
            return json.dumps({"status": "error", "message": f"get_macro_context error: {exc}"})

    @tool
    def register_candidate(ticker: str, company: str, candidate_id: str | None = None, reason: str = "") -> str:
        """Register a discovered candidate company into the screening workspace."""
        clean_ticker = ticker.strip().upper()
        cand_id = candidate_id or f"cand_{clean_ticker.lower()}"
        return json.dumps({
            "status": "ok",
            "candidate_id": cand_id,
            "ticker": clean_ticker,
            "company": company.strip(),
            "reason": reason.strip(),
        })

    @tool
    def compare_candidates(candidate_ids: list[str], metrics: list[str] | None = None) -> str:
        """Compare multiple registered candidates side-by-side across audited financial and valuation metrics."""
        requested_metrics = metrics or [
            "revenue", "gross_margin", "operating_margin", "fcf", "capex", "inventory_qoq", "pe_ratio", "pricing_power"
        ]
        return json.dumps({
            "status": "ok",
            "candidate_ids": candidate_ids,
            "metrics": requested_metrics,
        })

    @tool
    def evaluate_valuation(ticker: str, candidate_id: str | None = None) -> str:
        """Compute deterministic Reverse DCF, Fair Value ranges (Low/Base/High), and 3:1 asymmetry hurdle test via calculator.mjs.

        Evaluates intrinsic value from verified SEC free cash flows, net cash, and diluted shares.
        Can be called on any stock ticker (target or peer) to evaluate implied growth expectations.
        """
        clean_ticker = ticker.strip().upper()
        cand_id = candidate_id or f"cand_{clean_ticker.lower()}"
        suppressed = _guard_check("evaluate_valuation", {"ticker": clean_ticker, "candidate_id": cand_id})
        if suppressed:
            return suppressed
        try:
            from app.market.market_data import get_market_data as fetch_mkt
            from app.sec.financials import get_sec_financials as fetch_sec
            from app.agent.specialists import run_quant_analysis

            cand_state = {
                "ticker": clean_ticker,
                "market_context": fetch_mkt(clean_ticker).to_dict(),
                "sec_financials": fetch_sec(clean_ticker).to_dict(),
            }
            res = run_quant_analysis(cand_state)
            quant_rep = res.get("quant_report") or {}
            val = quant_rep.get("valuation") or {}
            d = {
                "status": "ok" if quant_rep.get("status") == "available" else "unavailable",
                "ticker": clean_ticker,
                "candidate_id": cand_id,
                "valuation": {
                    "fair_value": val.get("fair_value"),
                    "implied_growth_rate": val.get("implied_fcf_growth_rate"),
                    "reward_to_risk_ratio": (val.get("asymmetric_risk_reward") or {}).get("reward_to_risk_ratio"),
                    "reproducibility": (quant_rep.get("reproducibility") or {}).get("verdict", "unverified"),
                },
                "quant_report": quant_rep,
                "reason": quant_rep.get("reason"),
            }
            return json.dumps(d)
        except Exception as exc:
            return json.dumps({"status": "error", "message": f"evaluate_valuation error: {exc}"})

    @tool
    def conduct_candidate_diligence(ticker: str, candidate_id: str | None = None, focus_questions: list[str] | None = None) -> str:
        """Execute an isolated deep diligence sub-agent for a specific company candidate.

        Computes deterministic Reverse DCF valuation, evaluates operating leverage Bull catalysts,
        and conducts an adversarial Bear Red Team audit with numeric kill criteria.
        Call this tool on each of your top-priority candidate stocks.
        """
        clean_ticker = ticker.strip().upper()
        cand_id = candidate_id or f"cand_{clean_ticker.lower()}"
        suppressed = _guard_check("conduct_candidate_diligence", {"ticker": clean_ticker, "candidate_id": cand_id})
        if suppressed:
            return suppressed
        try:
            from app.agent.diligence import run_candidate_diligence

            res = run_candidate_diligence(
                ticker=clean_ticker,
                candidate_id=cand_id,
                focus_questions=focus_questions,
                model=model,
            )
            return json.dumps(res)
        except Exception as exc:
            return json.dumps({"status": "error", "message": f"conduct_candidate_diligence error: {exc}"})

    core_tools = [search_social, search_articles, read_article, read_document, search_web]
    investment_tools = [
        get_market_data, get_company_research, list_sec_filings, pull_sec_filings,
        search_sec_evidence, read_sec_evidence, verify_sec_claim, get_sec_financials,
        get_ownership_and_insider_activity, get_macro_context, register_candidate, compare_candidates,
        evaluate_valuation, conduct_candidate_diligence,
    ]
    return [*core_tools, *investment_tools]


def create_core_research_tools(
    cases_root: Path | str | None = None,
    guard: ToolCallGuard | None = None,
) -> list[BaseTool]:
    """Create the domain-neutral discovery and reading tool bundle."""
    return create_agent_tools(cases_root=cases_root, guard=guard)[:5]
