"""SEC Specialist Analyst capability sub-agent for deep filing investigation.

Donor provenance: retrieval and RRF reranking patterns adapted from
reference/enterprise-agentic-rag-platform-ara (app/agent.py:101-148).
EDGAR acquisition and filing parsing adapted from reference/edgartools.
Sub-agent synthesis contract and LangGraph StateGraph sub-agent architecture are locally written.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from app.sec.acquisition import list_sec_filings as _list_sec_filings
from app.sec.corpus import prepare_sec_corpus
from app.sec.embeddings import get_sec_embedder, get_sec_query_embedder
from app.sec.evidence import read_sec_evidence as _read_sec_evidence, search_sec_evidence as _search_sec_evidence
from app.sec.insiders import get_ownership_and_insider_activity as _get_ownership_and_insider_activity
from app.sec.pull import SelectedSecDocument, pull_sec_filings as _pull_sec_filings
from app.sec.retrieval import build_sec_index, search_sec_corpus
from app.storage.cases import case_path

logger = logging.getLogger(__name__)

SEC_ANALYST_SYSTEM_PROMPT = """You are a Senior SEC Filing Specialist and Forensic Auditor at an institutional investment fund.
Your mission is to read official SEC EDGAR disclosures (10-K, 10-Q, 8-K, Form 4) to answer specific investigative questions or verify material claims.

You have access to specialist SEC tools:
- list_filings: Query SEC EDGAR catalog for available 10-K, 10-Q, 8-K filings.
- pull_filing: Download and immediately index a selected filing into your local vector corpus.
- search_corpus: Hybrid semantic (dense FAISS) + lexical (sparse BM25) search with RRF reranking over the candidate's SEC corpus.
- read_chunk: Read verbatim chunks with context when you need to inspect footnotes, schedules, or tables.
- verify_claim: Test a specific factual claim against filings.
- get_ownership_and_insider_activity: Audit Form 4 insider trading (buys, sales, 10b5-1 plans).

NON-NEGOTIABLE OPERATIONAL AXIOMS:
1. Grounded In Real Filings: Base all conclusions strictly on retrieved filing excerpts. Never guess, assume, or invent information not present in the filings.
2. Exact Citations & Verbatim Quotes: Extract verbatim quotes and cite the exact Form, Filing Date, and SEC Accession Number for every material point.
3. Verification Rigor: If the task is verifying a rumor or claim, explicitly assess whether the official disclosure CONFIRMS it, CONTRADICTS it, or provides INSUFFICIENT evidence. Highlight discrepancies (e.g. non-binding LOI vs. claimed binding contract).
4. Multi-Filing Investigation: You can search multiple times with different queries, pull additional filings (e.g. 8-K or 10-Q) if referenced in footnotes, and cross-reference with insider trading.
5. Final Institutional Synthesis: When you have sufficient evidence, output your final synthesis strictly in valid JSON matching this exact structure:
{
  "assessment": "CONFIRMED | CONTRADICTED | INSUFFICIENT_EVIDENCE | INVESTIGATION_COMPLETE",
  "synthesis": "Comprehensive executive summary answering the question directly with citations.",
  "findings": [
    "Key finding 1 with quantitative detail...",
    "Key finding 2..."
  ]
}
"""


class SecAnalystState(TypedDict):
    """Execution state for the autonomous SEC analyst sub-agent graph."""

    messages: Annotated[Sequence[BaseMessage], add_messages]
    ticker: str
    candidate_id: str
    task: str
    turn_count: int
    evidence: list[dict[str, Any]]


def create_sec_subagent_tools(
    cases_root: Path,
    target_id: str,
    case_dir: Path,
    clean_ticker: str,
    cand_id: str,
) -> list[Any]:
    """Create private specialist tools for the SEC Analyst sub-agent."""

    @tool
    def list_filings(forms: list[str] | None = None, since: str | None = None) -> str:
        """List available SEC EDGAR filings for this company (e.g. forms=['10-K', '10-Q', '8-K'])."""
        try:
            disc_res = _list_sec_filings(ticker=clean_ticker, forms=forms, since=since)
            if disc_res.error:
                return json.dumps({"status": "error", "code": disc_res.error.code, "message": disc_res.error.message})
            filing_summaries = [
                {
                    "form": f.form,
                    "filing_date": str(f.filing_date),
                    "accession": f.accession,
                    "description": f.description or f"Form {f.form}",
                }
                for f in disc_res.filings[:15]
            ]
            return json.dumps({"status": "ok", "ticker": clean_ticker, "filings": filing_summaries})
        except Exception as exc:
            return json.dumps({"status": "error", "message": f"list_filings failed: {exc}"})

    @tool
    def pull_filing(form: str = "10-K", accession: str | None = None) -> str:
        """Download and immediately index a selected filing into the local vector corpus (Auto-Index on Pull)."""
        try:
            req_form = form.strip().upper()
            disc_res = _list_sec_filings(ticker=clean_ticker, forms=[req_form])
            if disc_res.error or not disc_res.filings:
                return json.dumps({"status": "unavailable", "message": f"No {req_form} filings found for ${clean_ticker}."})

            target_filing = None
            if accession:
                acc_clean = accession.strip()
                for f in disc_res.filings:
                    if f.accession == acc_clean:
                        target_filing = f
                        break
            if not target_filing:
                target_filing = disc_res.filings[0]

            sel = [
                SelectedSecDocument(
                    filing=target_filing,
                    document_name="primary_doc.htm",
                    source_url=target_filing.filing_url,
                )
            ]
            pull_res = _pull_sec_filings(cases_root=cases_root, case_id=target_id, selections=sel)
            if pull_res.error:
                return json.dumps({"status": "error", "code": pull_res.error.code, "message": pull_res.error.message})

            # Auto-Index on Pull
            prep_res = prepare_sec_corpus(case_dir)
            if prep_res.error is not None:
                return json.dumps({"status": "error", "code": "CORPUS_PREPARATION_FAILED", "message": str(prep_res.error)})
            build_sec_index(case_dir, embedder=get_sec_embedder())

            return json.dumps({
                "status": "ok",
                "message": f"Successfully pulled and indexed Form {target_filing.form} (Accession: {target_filing.accession}, Date: {target_filing.filing_date}). Ready for search.",
                "form": target_filing.form,
                "accession": target_filing.accession,
                "filing_date": str(target_filing.filing_date),
            })
        except Exception as exc:
            return json.dumps({"status": "error", "message": f"pull_filing failed: {exc}"})

    @tool
    def search_corpus(query: str, top_k: int = 5) -> str:
        """Run hybrid FAISS dense + BM25 sparse search over the candidate's indexed SEC filings."""
        try:
            index_file = case_dir / "sec" / "index" / "sec.faiss"
            raw_dir = case_dir / "sec" / "documents"
            if not index_file.exists():
                # Auto-heal: build index if raw documents exist
                if raw_dir.exists() and any(raw_dir.glob("*.htm*")):
                    prep_res = prepare_sec_corpus(case_dir)
                    if prep_res.error is None:
                        build_sec_index(case_dir, embedder=get_sec_embedder())
                else:
                    return json.dumps({
                        "status": "unavailable",
                        "code": "no_filings_pulled",
                        "message": f"No SEC filings pulled yet for ${clean_ticker}. Call list_filings to inspect catalog, then pull_filing to acquire the filing before searching.",
                    })

            embed_query = get_sec_query_embedder()
            retrieval = search_sec_corpus(case_dir, query, embed_query=embed_query)
            if retrieval.error:
                return json.dumps({"status": "error", "code": retrieval.error.code, "message": retrieval.error.message})
            if not retrieval.results:
                return json.dumps({"status": "ok", "results": [], "message": f"No matching sections found for query: '{query}'"})

            items = []
            for r in retrieval.results[:top_k]:
                chunk = r.chunk
                score_val = r.rerank_score if r.rerank_score is not None else r.rrf_score
                items.append({
                    "chunk_id": chunk.chunk_id,
                    "form": chunk.form,
                    "filing_date": str(chunk.filing_date),
                    "accession": chunk.accession,
                    "document": chunk.document_name,
                    "source_url": chunk.source_url,
                    "quote": chunk.text[:1500],
                    "score": round(float(score_val), 4),
                })
            return json.dumps({"status": "ok", "results": items})
        except Exception as exc:
            return json.dumps({"status": "error", "message": f"search_corpus failed: {exc}"})

    @tool
    def read_chunk(chunk_ids: list[str]) -> str:
        """Read exact SEC filing text chunks with surrounding context for footnotes, schedules, or tables."""
        try:
            receipts, err = _read_sec_evidence(case_directory=case_dir, chunk_ids=chunk_ids, candidate_id=cand_id)
            if err:
                return json.dumps({"status": "error", **err})
            return json.dumps({"status": "ok", "chunks": receipts})
        except Exception as exc:
            return json.dumps({"status": "error", "message": f"read_chunk failed: {exc}"})

    @tool
    def verify_claim(claim: str) -> str:
        """Verify a specific factual claim or rumor against the local SEC filings."""
        try:
            from app.sec.default_assessor import get_default_sec_assessor
            from app.sec.verifier import verify_sec_claim as _verify_sec_claim

            assessor = get_default_sec_assessor()
            embed_q = get_sec_query_embedder()
            res = _verify_sec_claim(case_dir, claim, assessor=assessor, embed_query=embed_q)
            if res.error:
                return json.dumps({"status": "error", "code": res.error.code, "message": res.error.message})
            return json.dumps({"status": "ok", "verification": res.verification.to_dict() if res.verification else {}})
        except Exception as exc:
            return json.dumps({"status": "error", "message": f"verify_claim failed: {exc}"})

    @tool
    def get_ownership_and_insider_activity(limit: int = 20) -> str:
        """Audit Form 4 insider transactions, isolating open-market buys/sales from tax withholding."""
        try:
            res = _get_ownership_and_insider_activity(clean_ticker, candidate_id=cand_id, limit=limit)
            return json.dumps(res)
        except Exception as exc:
            return json.dumps({"status": "error", "message": f"get_ownership_and_insider_activity failed: {exc}"})

    return [list_filings, pull_filing, search_corpus, read_chunk, verify_claim, get_ownership_and_insider_activity]


def create_sec_analyst_subgraph(model_with_tools: Any, tools: Sequence[Any], max_turns: int = 6):
    """Compile the LangGraph StateGraph for the autonomous SEC Analyst sub-agent."""
    tool_node = ToolNode(tools)

    def analyst_node(state: SecAnalystState) -> dict[str, Any]:
        response = model_with_tools.invoke(state["messages"])
        return {
            "messages": [response],
            "turn_count": state.get("turn_count", 0) + 1,
        }

    def should_continue(state: SecAnalystState) -> Literal["tools", "__end__"]:
        messages = state.get("messages", [])
        last_msg = messages[-1] if messages else None
        tool_calls = getattr(last_msg, "tool_calls", None) if last_msg else None
        if tool_calls and state.get("turn_count", 0) < max_turns:
            return "tools"
        return END

    def ingest_subagent_results(state: SecAnalystState) -> dict[str, Any]:
        messages = state.get("messages", [])
        start = len(messages)
        while start and isinstance(messages[start - 1], ToolMessage):
            start -= 1
        new_evidence = list(state.get("evidence") or [])
        for msg in messages[start:]:
            if isinstance(msg, ToolMessage) and msg.content:
                try:
                    payload = json.loads(msg.content)
                    if isinstance(payload, dict):
                        # Extract chunks from search_corpus
                        for item in payload.get("results") or []:
                            if isinstance(item, dict) and item.get("quote"):
                                if not any(e.get("chunk_id") == item.get("chunk_id") for e in new_evidence):
                                    new_evidence.append(item)
                        # Extract chunks from read_chunk
                        for item in payload.get("chunks") or []:
                            if isinstance(item, dict) and item.get("excerpt"):
                                ev_item = {
                                    "chunk_id": item.get("chunk_id"),
                                    "form": item.get("form"),
                                    "filing_date": item.get("filing_date"),
                                    "accession": item.get("accession"),
                                    "quote": item.get("excerpt"),
                                    "score": 1.0,
                                }
                                if not any(e.get("chunk_id") == ev_item.get("chunk_id") for e in new_evidence):
                                    new_evidence.append(ev_item)
                except Exception:
                    pass
        return {"evidence": new_evidence}

    workflow = StateGraph(SecAnalystState)
    workflow.add_node("analyst", analyst_node)
    workflow.add_node("tools", tool_node)
    workflow.add_node("ingest", ingest_subagent_results)

    workflow.add_edge(START, "analyst")
    workflow.add_conditional_edges("analyst", should_continue, {"tools": "tools", END: END})
    workflow.add_edge("tools", "ingest")
    workflow.add_edge("ingest", "analyst")

    return workflow.compile()


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
    """Execute an autonomous SEC filing research investigation for one company.

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

    subagent_tools = create_sec_subagent_tools(
        cases_root=root,
        target_id=target_id,
        case_dir=case_dir,
        clean_ticker=clean_ticker,
        cand_id=cand_id,
    )

    # 1. Full Autonomous LangGraph Sub-Agent Path (when model supports tool binding)
    if model is not None and hasattr(model, "bind_tools"):
        try:
            model_with_tools = model.bind_tools(subagent_tools)
            subgraph = create_sec_analyst_subgraph(model_with_tools, subagent_tools, max_turns=6)

            initial_human_prompt = (
                f"Conduct an institutional SEC filing investigation for ${clean_ticker}.\n"
                f"Task: {task}\n"
                f"Target Form Hint: {form or '10-K, 10-Q, or 8-K'}\n\n"
                "Use your tools (list_filings, pull_filing, search_corpus, read_chunk, verify_claim, get_ownership_and_insider_activity) "
                "as needed to find primary evidence, and conclude with your final institutional synthesis in strictly valid JSON."
            )
            initial_state: SecAnalystState = {
                "messages": [
                    SystemMessage(content=SEC_ANALYST_SYSTEM_PROMPT),
                    HumanMessage(content=initial_human_prompt),
                ],
                "ticker": clean_ticker,
                "candidate_id": cand_id,
                "task": task,
                "turn_count": 0,
                "evidence": [],
            }

            final_sub_state = subgraph.invoke(initial_state)
            messages = final_sub_state.get("messages", [])
            last_msg = messages[-1] if messages else None
            raw_text = str(getattr(last_msg, "content", "")).strip() if last_msg else ""
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            elif raw_text.startswith("```"):
                raw_text = raw_text[3:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]

            parsed = json.loads(raw_text.strip()) if raw_text.strip() else {}
            collected_ev = list(final_sub_state.get("evidence") or [])
            return {
                "status": "ok",
                "ticker": clean_ticker,
                "candidate_id": cand_id,
                "task": task,
                "assessment": parsed.get("assessment", "INVESTIGATION_COMPLETE"),
                "synthesis": parsed.get("synthesis", "Filing excerpts reviewed by SEC specialist sub-agent."),
                "findings": parsed.get("findings", []),
                "evidence": collected_ev,
            }
        except Exception as exc:
            logger.warning("Autonomous SEC analyst sub-agent execution encountered (%s); falling back to direct retrieval", exc)

    # 2. Deterministic 1-Pass Retrieval Fallback (for test doubles or non-tool-calling models)
    index_file = case_dir / "sec" / "index" / "sec.faiss"
    if not index_file.exists():
        forms_to_search = [form.strip().upper()] if form else ["10-K", "10-Q", "8-K"]
        disc_res = _list_sec_filings(ticker=clean_ticker, forms=forms_to_search)
        if disc_res.filings:
            selected_docs = [
                SelectedSecDocument(
                    filing=f,
                    document_name="primary_doc.htm",
                    source_url=f.filing_url,
                )
                for f in disc_res.filings[:2]
            ]
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
