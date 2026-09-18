"""SEC Specialist Analyst capability sub-agent for deep filing investigation.

Donor provenance: retrieval and RRF reranking patterns adapted from
reference/enterprise-agentic-rag-platform-ara (app/agent.py:101-148).
EDGAR acquisition and filing parsing adapted from reference/edgartools.
Sub-agent synthesis contract is locally written.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.sec.acquisition import list_sec_filings as _list_sec_filings
from app.sec.corpus import prepare_sec_corpus
from app.sec.embeddings import get_sec_embedder, get_sec_query_embedder
from app.sec.pull import SelectedSecDocument, pull_sec_filings as _pull_sec_filings
from app.sec.retrieval import build_sec_index, search_sec_corpus
from app.storage.cases import case_path

logger = logging.getLogger(__name__)

SEC_ANALYST_SYSTEM_PROMPT = """You are a Senior SEC Filing Specialist and Forensic Auditor at an institutional investment fund.
Your mission is to read official SEC EDGAR disclosures (10-K, 10-Q, 8-K, Form 4) to answer specific investigative questions or verify material claims.

NON-NEGOTIABLE OPERATIONAL AXIOMS:
1. Grounded In Real Filings: Base all conclusions strictly on the provided filing excerpts. Never guess, assume, or invent information not present in the excerpts.
2. Exact Citations & Verbatim Quotes: Extract verbatim quotes and cite the exact Form, Filing Date, and SEC Accession Number for every material point.
3. Verification Rigor: If the task is verifying a rumor or claim, explicitly assess whether the official disclosure CONFIRMS it, CONTRADICTS it, or provides INSUFFICIENT evidence. Highlight discrepancies (e.g. non-binding LOI vs. claimed binding contract).
4. Concise Institutional Synthesis: Provide a 2-4 sentence executive synthesis followed by bulleted key findings.

Return strictly valid JSON matching this exact structure:
{
  "assessment": "CONFIRMED | CONTRADICTED | INSUFFICIENT_EVIDENCE | INVESTIGATION_COMPLETE",
  "synthesis": "Comprehensive executive summary answering the question directly with citations.",
  "findings": [
    "Key finding 1 with quantitative detail...",
    "Key finding 2..."
  ]
}
"""


def run_sec_investigation(
    cases_root: Path | str,
    case_id: str,
    ticker: str,
    task: str,
    form: str | None = None,
    candidate_id: str | None = None,
    model: Any | None = None,
    top_k: int = 5,
) -> dict[str, Any]:
    """Execute an isolated SEC filing research investigation for one company.

    Args:
        cases_root: Root directory for case workspaces.
        case_id: Active case identifier.
        ticker: Target equity ticker symbol.
        task: Research question or claim to investigate.
        form: Optional SEC form filter (e.g. '10-K', '10-Q', '8-K').
        candidate_id: Optional owning candidate identifier.
        model: Optional LLM instance for specialist synthesis.
        top_k: Number of hybrid RAG chunks to retrieve.

    Returns:
        Structured dictionary containing synthesis, assessment, and evidence receipts.
    """
    clean_ticker = ticker.strip().upper()
    cand_id = candidate_id or f"cand_{clean_ticker.lower()}"
    root = Path(cases_root)

    target_id = f"{case_id}/candidates/{cand_id}" if cand_id else case_id
    try:
        case_dir = case_path(root, target_id)
    except ValueError:
        case_dir = root / target_id

    # 1. Check or build local index
    index_file = case_dir / "sec" / "index" / "sec.faiss"
    if not index_file.exists():
        # Auto-discover filings if not present
        forms_to_search = [form.strip().upper()] if form else ["10-K", "10-Q", "8-K"]
        disc_res = _list_sec_filings(ticker=clean_ticker, forms=forms_to_search)
        if disc_res.filings:
            selected_docs = []
            for f in disc_res.filings[:2]:
                selected_docs.append(
                    SelectedSecDocument(
                        filing=f,
                        document_name="primary_doc.htm",
                        source_url=f.filing_url,
                    )
                )
            _pull_sec_filings(cases_root=root, case_id=target_id, selections=selected_docs)
            prep_res = prepare_sec_corpus(case_dir)
            if prep_res.error is None:
                build_sec_index(case_dir, embedder=get_sec_embedder())

    # If index still doesn't exist (no filings found or pull failed), return graceful notice
    if not index_file.exists():
        return {
            "status": "unavailable",
            "ticker": clean_ticker,
            "candidate_id": cand_id,
            "task": task,
            "assessment": "INSUFFICIENT_EVIDENCE",
            "synthesis": f"No local SEC filings could be retrieved for ${clean_ticker}.",
            "findings": [],
            "evidence": [],
        }

    # 2. Hybrid FAISS dense + BM25 sparse retrieval
    embed_query = get_sec_query_embedder()
    retrieval = search_sec_corpus(case_dir, task, embed_query=embed_query)
    if retrieval.error or not retrieval.results:
        return {
            "status": "ok",
            "ticker": clean_ticker,
            "candidate_id": cand_id,
            "task": task,
            "assessment": "INSUFFICIENT_EVIDENCE",
            "synthesis": f"SEC filing corpus searched, but no sections relevant to '{task}' were found.",
            "findings": [],
            "evidence": [],
        }

    # Format retrieved evidence chunks
    evidence_list = []
    chunk_texts_for_prompt = []
    for idx, item in enumerate(retrieval.results[:top_k], start=1):
        chunk = item.chunk
        score_val = item.rerank_score if item.rerank_score is not None else item.rrf_score
        ev = {
            "quote": chunk.text,
            "form": chunk.form,
            "filing_date": str(chunk.filing_date),
            "accession": chunk.accession,
            "document": chunk.document_name,
            "source_url": chunk.source_url,
            "score": round(float(score_val), 4),
        }
        evidence_list.append(ev)
        chunk_texts_for_prompt.append(
            f"--- Excerpt {idx} (Form: {chunk.form} | Date: {chunk.filing_date} | Accession: {chunk.accession}) ---\n{chunk.text}"
        )

    # 3. Model synthesis if model provided
    if model is not None and hasattr(model, "invoke"):
        try:
            human_prompt = f"""Investigate the following SEC question/claim for ${clean_ticker}:
Task: {task}

Retrieved SEC Filing Excerpts:
{chr(10).join(chunk_texts_for_prompt)}

Answer the task directly based on these filings in strictly valid JSON."""

            resp = model.invoke([
                SystemMessage(content=SEC_ANALYST_SYSTEM_PROMPT),
                HumanMessage(content=human_prompt),
            ])
            raw_text = str(getattr(resp, "content", "")).strip()
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            elif raw_text.startswith("```"):
                raw_text = raw_text[3:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]
            parsed = json.loads(raw_text.strip())

            return {
                "status": "ok",
                "ticker": clean_ticker,
                "candidate_id": cand_id,
                "task": task,
                "assessment": parsed.get("assessment", "INVESTIGATION_COMPLETE"),
                "synthesis": parsed.get("synthesis", "Filing excerpts reviewed."),
                "findings": parsed.get("findings", []),
                "evidence": evidence_list,
            }
        except Exception as exc:
            logger.warning("SEC analyst model synthesis failed (%s); using direct excerpts", exc)

    # Offline / deterministic fallback
    summary_text = f"Found {len(evidence_list)} relevant SEC excerpts for ${clean_ticker}."
    return {
        "status": "ok",
        "ticker": clean_ticker,
        "candidate_id": cand_id,
        "task": task,
        "assessment": "INVESTIGATION_COMPLETE",
        "synthesis": summary_text,
        "findings": [e["quote"][:150] + "..." for e in evidence_list[:3]],
        "evidence": evidence_list,
    }
