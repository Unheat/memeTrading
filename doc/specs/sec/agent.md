# Module Spec — `app/sec/agent.py`

## Responsibility

Implement the High-Leverage SEC Specialist Sub-Agent capability (`run_sec_investigation`).
The sub-agent executes an isolated, end-to-end filing investigation for one candidate company:
1. Resolves CIK / ticker via `app.sec.identity`.
2. Auto-discovers relevant official SEC filings matching form filters (e.g. 10-K, 10-Q, 8-K) via `app.sec.acquisition.list_sec_filings`.
3. Auto-pulls primary documents and material exhibits to the case-local corpus via `app.sec.pull.pull_sec_filings` if not already indexed.
4. Chunks and builds the local hybrid FAISS dense vector + BM25 sparse index via `prepare_sec_corpus` and `build_sec_index`.
5. Executes hybrid RAG search with Reciprocal Rank Fusion (RRF) for the top-k chunks matching the research question or claim.
6. A specialized SEC Analyst LLM reads the retrieved excerpts and synthesizes a concise, grounded research response citing exact accession numbers, filing forms, dates, and verbatim quotes.
7. Auto-formats verified evidence quotes for ingestion into candidate workspaces.

## Public contracts

### `run_sec_investigation(cases_root, case_id, ticker, task, form=None, candidate_id=None, model=None, top_k=5)`

- `cases_root`: Root path for case workspaces.
- `case_id`: Session case reference.
- `ticker`: Target company equity ticker.
- `task`: Research question or hypothesis to investigate against filings.
- `form`: Optional filing form filter (e.g. "10-K", "10-Q", "8-K").
- `candidate_id`: Optional candidate workspace reference.
- `model`: Optional injected language model for specialist synthesis.
- `top_k`: Number of hybrid chunks to retrieve and analyze.

Returns a dictionary matching:
```json
{
  "status": "ok",
  "ticker": "MSFT",
  "candidate_id": "cand_msft",
  "task": "...",
  "assessment": "INVESTIGATION_COMPLETE | CONFIRMED | CONTRADICTED | INSUFFICIENT_EVIDENCE",
  "synthesis": "Comprehensive executive summary answering the question directly with citations.",
  "findings": [
    "Key finding 1...",
    "Key finding 2..."
  ],
  "evidence": [
    {
      "quote": "...",
      "form": "10-K",
      "filing_date": "2026-02-01",
      "accession": "0000789019-26-000001",
      "document": "primary_doc.htm",
      "source_url": "https://www.sec.gov/...",
      "score": 0.0333
    }
  ]
}
```

## Donor code provenance

| Local symbol | Reuse type | Exact donor location | Deliberate changes |
| --- | --- | --- | --- |
| `run_sec_investigation` hybrid search & RRF | adapted | `reference/enterprise-agentic-rag-platform-ara/app/agent.py:101-148`, retrieve & grade | Reuses case-local hybrid FAISS + BM25 index and Reciprocal Rank Fusion; wraps retrieval in an automated filing discovery and pull cycle with structured evidence citations. |
| EDGAR acquisition & parsing | adapted | `reference/edgartools`, company filings API | Integrated via `app.sec.acquisition` and `app.sec.pull` with local rate-limiting and SEC User-Agent compliance. |
| `SEC_ANALYST_SYSTEM_PROMPT` | locally written | N/A | Written locally with institutional buyside axioms, verbatim quote extraction, and strict JSON schema. |
