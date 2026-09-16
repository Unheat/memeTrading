"""Tests for durable evidence ledger generation and source/excerpt persistence."""
import json
from langchain_core.messages import ToolMessage
from app.agent.tool_result_ingestion import ingest_tool_results


def test_read_document_populates_source_and_excerpt_ledger():
    """Verify read_document creates stable source_id, sha256, and citation excerpts."""
    doc_payload = {
        "status": "ok",
        "url": "https://example.com/ir/presentation.pdf",
        "title": "Q2 Investor Presentation",
        "text": "Enterprise cloud ARR reached $1.2B with 35% operating margin.",
        "candidate_id": "cand_msft",
    }
    messages = [ToolMessage(content=json.dumps(doc_payload), name="read_document", tool_call_id="call-doc-1")]

    state = {"candidates": {"cand_msft": {"ticker": "MSFT"}}}
    update = ingest_tool_results(state, messages)

    # Source record checks
    assert len(update["source_records"]) == 1
    src = update["source_records"][0]
    assert src["source_id"].startswith("src_")
    assert src["status"] == "read"
    assert src["candidate_id"] == "cand_msft"
    assert len(src["content_sha256"]) == 64

    # Excerpt checks in evidence
    assert len(update["evidence"]) == 1
    exc = update["evidence"][0]
    assert exc["excerpt_id"].startswith("exc_")
    assert exc["source_id"] == src["source_id"]
    assert "Enterprise cloud ARR" in exc["quote"]


def test_source_deduplication_promotes_discovered_to_read():
    """Verify a discovered URL is upgraded to read status when read_document executes."""
    state = {
        "source_records": [{
            "source_id": "src_1",
            "url": "https://example.com/deck.pdf",
            "title": "Deck",
            "status": "discovered",
        }]
    }
    doc_payload = {
        "status": "ok",
        "url": "https://example.com/deck.pdf",
        "title": "Deck",
        "text": "Full document content read.",
    }
    messages = [ToolMessage(content=json.dumps(doc_payload), name="read_document", tool_call_id="call-doc-2")]
    update = ingest_tool_results(state, messages)

    assert len(update["source_records"]) == 1
    src = update["source_records"][0]
    assert src["status"] == "read"
    assert src["content_sha256"] != ""
