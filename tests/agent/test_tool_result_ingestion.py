"""Focused tests for deterministic tool-result ingestion."""
import json

from langchain_core.messages import ToolMessage

from app.agent.tool_result_ingestion import ingest_tool_results


def _message(name: str, call_id: str, payload: object) -> ToolMessage:
    """Build a JSON ToolMessage for tests.

    Args:
        name: Tool name used for deterministic routing.
        call_id: Tool call identifier retained in receipts.
        payload: JSON-serializable result value.

    Returns:
        LangChain ToolMessage containing serialized payload.
    """
    return ToolMessage(content=json.dumps(payload), name=name, tool_call_id=call_id)


def test_parallel_results_merge_without_losing_existing_state() -> None:
    """Verify parallel successful results produce one lossless merged update."""
    state = {
        "evidence": [{"existing": "evidence"}],
        "contradictions": [{"existing": "contradiction"}],
        "sec_corpora": ["old-corpus"],
        "searches_performed": [{"tool": "old", "status": "ok"}],
    }
    messages = [
        _message("get_market_data", "market-1", {"ticker": "MU", "provider": "test"}),
        _message("get_company_research", "research-1", {"ticker": "MU", "ratings": {"buy": 4}}),
        _message("pull_sec_filings", "pull-1", {"status": "ok", "corpus": {"corpus_id": "new-corpus"}}),
        _message(
            "verify_sec_claim",
            "verify-1",
            {
                "status": "ok",
                "verification": {
                    "claim": "Revenue grew",
                    "verdict": "PARTIALLY_CONFIRMED",
                    "confidence": 0.8,
                    "evidence_for": [{"chunk_id": "chunk-1", "quote": "Revenue grew 8%."}],
                    "evidence_against": [{"chunk_id": "chunk-2", "quote": "Units declined."}],
                },
            },
        ),
        _message(
            "verify_sec_claim",
            "verify-2",
            {
                "status": "ok",
                "verification": {
                    "claim": "Margins expanded",
                    "verdict": "CONFIRMED",
                    "confidence": 0.6,
                    "evidence_for": [{"chunk_id": "chunk-3", "quote": "Margin expanded."}],
                    "evidence_against": [],
                },
            },
        ),
    ]

    update = ingest_tool_results(state, messages)

    assert update["market_context"]["provider"] == "test"
    assert update["consensus_snapshot"]["ratings"] == {"buy": 4}
    assert update["sec_corpora"] == ["old-corpus", "new-corpus"]
    assert [item.get("chunk_id") for item in update["evidence"]] == [None, "chunk-1", "chunk-3"]
    assert [item.get("chunk_id") for item in update["contradictions"]] == [None, "chunk-2"]
    assert update["confidence"] == 0.6
    assert len(update["searches_performed"]) == 6
    assert [receipt["tool_call_id"] for receipt in update["searches_performed"][1:]] == [
        "market-1", "research-1", "pull-1", "verify-1", "verify-2"
    ]


def test_errors_duplicates_and_bad_json_are_receipts_not_evidence() -> None:
    """Verify failed and duplicate results remain auditable but never become evidence."""
    messages = [
        _message("verify_sec_claim", "error-1", {"status": "error", "code": "SEC_DOWN", "message": "unavailable", "verification": {"evidence_for": [{"quote": "bad"}], "confidence": 1.0}}),
        _message("verify_sec_claim", "duplicate-1", {"status": "duplicate_suppressed", "message": "already performed", "verification": {"evidence_against": [{"quote": "bad"}]}}),
        ToolMessage(content="not json", name="search_web", tool_call_id="parse-1"),
    ]

    update = ingest_tool_results({}, messages)

    assert update["evidence"] == []
    assert update["contradictions"] == []
    assert "confidence" not in update
    assert update["searches_performed"] == [
        {"tool": "verify_sec_claim", "tool_call_id": "error-1", "status": "error", "error": "unavailable", "code": "SEC_DOWN"},
        {"tool": "verify_sec_claim", "tool_call_id": "duplicate-1", "status": "duplicate_suppressed", "error": "already performed"},
        {"tool": "search_web", "tool_call_id": "parse-1", "status": "error", "error": "invalid JSON: Expecting value"},
    ]


def test_tool_name_controls_routing_and_corpus_ids_are_deduplicated() -> None:
    """Verify payload shape cannot bypass tool routing and corpus IDs stay unique."""
    messages = [
        _message("search_web", "web-1", {"ticker": "MU", "provider": "not-market"}),
        _message("pull_sec_filings", "pull-1", {"status": "ok", "corpus": {"corpus_id": "same"}}),
        _message("pull_sec_filings", "pull-2", {"status": "ok", "corpus": {"corpus_id": "same"}}),
    ]

    update = ingest_tool_results({"sec_corpora": ["same"]}, messages)

    assert "market_context" not in update
    assert update["sec_corpora"] == ["same"]
    assert len(update["searches_performed"]) == 3
