"""Controlled end-to-end coverage for every registered research tool."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from langchain_core.messages import AIMessage

from app.agent.graph import create_research_graph
from app.agent.state import ResearchRequest, create_initial_state
from app.agent.tools import create_agent_tools
from app.sec.acquisition import FilingDiscoveryResult
from app.sec.schemas import FilingMetadata


class ToolCoverageModel:
    """Issue every safe registered tool in dependency-safe research order."""

    def __init__(self) -> None:
        """Initialize the deterministic conversation step."""
        self.step = 0

    def bind_tools(self, tools):
        """Accept the full tool registry."""
        return self

    def invoke(self, messages):
        """Return staged calls for discovery, collection, then verification/comparison."""
        self.step += 1
        if self.step == 1:
            calls = [
                ("search_social", {"query": "MSFT cloud demand"}),
                ("search_articles", {"query": "MSFT cloud demand"}),
                ("search_web", {"query": "MSFT investor relations", "file_type": "pdf"}),
                ("read_article", {"url": "https://example.test/msft"}),
                ("register_candidate", {"ticker": "MSFT", "company": "Microsoft", "candidate_id": "cand_msft"}),
                ("read_document", {"url": "https://example.test/msft-deck.pdf", "candidate_id": "cand_msft"}),
            ]
        elif self.step == 2:
            calls = [
                ("get_market_data", {"ticker": "MSFT", "candidate_id": "cand_msft"}),
                ("get_company_research", {"ticker": "MSFT", "candidate_id": "cand_msft"}),
                ("get_sec_financials", {"ticker": "MSFT", "candidate_id": "cand_msft"}),
                ("get_macro_context", {"series_ids": ["DGS10", "FEDFUNDS"]}),
                ("get_ownership_and_insider_activity", {"ticker": "MSFT", "candidate_id": "cand_msft"}),
                ("list_sec_filings", {"ticker": "MSFT", "forms": ["10-K"], "since": "2026-01-01", "candidate_id": "cand_msft"}),
                ("pull_sec_filings", {"case_id": "coverage", "candidate_id": "cand_msft", "selections": [{"ticker": "MSFT", "cik": "789019", "form": "10-K", "filing_date": "2026-02-01", "accession": "0000789019-26-000001", "filing_url": "https://www.sec.gov/Archives/edgar/data/789019/000078901926000001/form10k.htm"}]}),
            ]
        elif self.step == 3:
            calls = [
                ("search_sec_evidence", {"case_id": "coverage", "candidate_id": "cand_msft", "query": "cloud gross margin"}),
                ("read_sec_evidence", {"case_id": "coverage", "candidate_id": "cand_msft", "chunk_ids": ["chunk-1"]}),
                ("verify_sec_claim", {"corpus_id": "coverage/candidates/cand_msft", "candidate_id": "cand_msft", "claim": "Microsoft reported cloud growth."}),
                ("investigate_sec", {"ticker": "MSFT", "task": "Check datacenter capex", "candidate_id": "cand_msft"}),
                ("compare_candidates", {"candidate_ids": ["cand_msft"], "metrics": ["revenue"]}),
                ("conduct_candidate_diligence", {"ticker": "MSFT", "candidate_id": "cand_msft"}),
                ("evaluate_valuation", {"ticker": "MSFT", "candidate_id": "cand_msft"}),
            ]
        else:
            return AIMessage(content="Microsoft is the only evidence-backed candidate collected; the requested one-company ranking is complete.")
        return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"coverage-{self.step}-{index}", "type": "tool_call"} for index, (name, args) in enumerate(calls)])


def _result(payload: dict):
    """Return a minimal provider result object with the requested payload."""
    return SimpleNamespace(to_dict=lambda: payload)


def test_e2e_every_registered_tool_persists_owned_receipts(monkeypatch, tmp_path: Path) -> None:
    """Exercise every tool and inspect universal graph artifacts without network access."""
    import app.agent.tools as tools_module
    import app.sec.default_assessor as assessor_module
    import app.sec.embeddings as embeddings_module

    monkeypatch.setattr(tools_module, "_search_social", lambda **_: _result({"status": "ok", "posts": [{"url": "https://example.test/social", "title": "Social signal"}]}))
    monkeypatch.setattr(tools_module, "_search_articles", lambda **_: _result({"status": "ok", "articles": [{"url": "https://example.test/article", "title": "Article"}]}))
    monkeypatch.setattr(tools_module, "_search_web", lambda **_: _result({"status": "ok", "results": [{"url": "https://example.test/web", "title": "Web"}]}))
    monkeypatch.setattr(tools_module, "_read_article", lambda **_: _result({"status": "ok", "url": "https://example.test/msft", "title": "Read article"}))
    monkeypatch.setattr(tools_module, "_read_document", lambda **_: {"status": "ok", "url": "https://example.test/msft-deck.pdf", "text": "Read document text", "discovered_documents": []})
    monkeypatch.setattr(tools_module, "_get_market_data", lambda **_: _result({"status": "ok", "ticker": "MSFT", "quote": {"price": 450.0}, "currency": "USD", "as_of": "2026-09-16", "addv_20d": {"value": 1_000_000}}))
    monkeypatch.setattr(tools_module, "_get_company_research", lambda **_: _result({"status": "ok", "ticker": "MSFT", "ratings": {"buy": 10}}))
    monkeypatch.setattr(tools_module, "_get_sec_financials", lambda **_: _result({"status": "ok", "ticker": "MSFT", "periods": ["2026-Q2"]}))
    monkeypatch.setattr(tools_module, "_get_macro_context", lambda **_: {"DGS10": {"latest_value": 4.15, "status": "ok"}})
    monkeypatch.setattr(tools_module, "_get_ownership_and_insider_activity", lambda **_: {"status": "ok", "ticker": "MSFT", "transactions": [{"name": "Satya Nadella", "transaction_code": "S"}]})
    filing = FilingMetadata(ticker="MSFT", cik="789019", form="10-K", filing_date=__import__("datetime").date(2026, 2, 1), accession="0000789019-26-000001", filing_url="https://www.sec.gov/Archives/edgar/data/789019/000078901926000001/form10k.htm")
    monkeypatch.setattr(tools_module, "_list_sec_filings", lambda **_: FilingDiscoveryResult((filing,)))
    corpus = SimpleNamespace(to_dict=lambda: {"corpus_id": "coverage/candidates/cand_msft", "cik": "789019"})
    monkeypatch.setattr(tools_module, "_pull_sec_filings", lambda **_: SimpleNamespace(error=None, corpus=corpus))
    monkeypatch.setattr(tools_module, "_search_sec_evidence", lambda **_: ([{"chunk_id": "chunk-1", "excerpt": "Cloud revenue grew."}], None))
    monkeypatch.setattr(tools_module, "_read_sec_evidence", lambda **_: ([{"chunk_id": "chunk-1", "text": "Cloud revenue grew by 20% in Q2."}], None))
    monkeypatch.setattr(tools_module, "_verify_sec_claim", lambda **_: SimpleNamespace(error=None, verification=SimpleNamespace(to_dict=lambda: {"claim": "Microsoft reported cloud growth.", "verdict": "CONFIRMED", "confidence": 0.9, "evidence_for": [{"quote": "Cloud revenue grew.", "source_url": "https://www.sec.gov/example"}], "evidence_against": []})))
    monkeypatch.setattr("app.sec.agent.run_sec_investigation", lambda **_: {"status": "ok", "ticker": "MSFT", "candidate_id": "cand_msft", "task": "Check datacenter capex", "synthesis": "Datacenter capex verified.", "evidence": [{"quote": "Cloud revenue grew.", "source_url": "https://www.sec.gov/example"}]})
    monkeypatch.setattr(embeddings_module, "get_sec_query_embedder", lambda: object())
    monkeypatch.setattr(assessor_module, "get_default_sec_assessor", lambda: object())

    # The verify wrapper skips corpus preparation when the candidate index exists.
    index = tmp_path / "coverage" / "candidates" / "cand_msft" / "sec" / "index" / "sec.faiss"
    index.parent.mkdir(parents=True)
    index.write_text("placeholder", encoding="utf-8")
    initial = create_initial_state(ResearchRequest(query="Rank the best 1 cloud company", requested_ranking_count=1), "coverage")
    final = create_research_graph(ToolCoverageModel(), create_agent_tools(cases_root=tmp_path)).invoke(initial)

    tool_names = {receipt["tool"] for receipt in final["searches_performed"]}
    assert tool_names == {tool.name for tool in create_agent_tools(cases_root=tmp_path)}
    assert not [receipt for receipt in final["searches_performed"] if receipt["status"] == "error"]
    assert final["status"] == "completed"
    assert final["market_context"] is None
    candidate = final["candidates"]["cand_msft"]
    assert candidate["market_context"]["ticker"] == "MSFT"
    assert candidate["sec_corpora"] == ["coverage/candidates/cand_msft"]
    assert candidate["evidence"][0]["source_url"] == "https://www.sec.gov/example"
    assert candidate["insider_activity"]["ticker"] == "MSFT"
    assert len(candidate["sec_evidence_excerpts"]) >= 2
    assert final["capability_outputs"]["macro_context"]["macro_series"]["DGS10"]["latest_value"] == 4.15
    assert "MSFT" in final["comparisons"][0]["candidate_values"]
    assert final["comparisons"][0]["metric_key"] == "revenue"

    from app.agent.memo import render_research_report
    report = render_research_report(final, "All 17 tools verified and evidence compiled.")
    assert "Requested ranking count: 1" in report
    assert "MSFT" in report
    assert "yes" in report  # market and sec evidence coverage yes!
