"""Deterministically ingest tool results into universal research state.

This module is locally written; it contains no copied or adapted donor code.
"""
from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from typing import Any

from langchain_core.messages import ToolMessage

_ERROR_STATUSES = frozenset({"error", "duplicate_suppressed"})
_CANDIDATE_SCOPED_TOOLS = frozenset({
    "get_market_data", "get_sec_financials", "get_company_research", "list_sec_filings",
    "pull_sec_filings", "verify_sec_claim", "search_sec_evidence", "read_sec_evidence",
    "get_ownership_and_insider_activity", "read_document",
})


def _clean_non_finite(obj: Any) -> Any:
    """Recursively convert float NaN and infinity values to ``None``."""
    if isinstance(obj, float):
        return None if math.isnan(obj) or math.isinf(obj) else obj
    if isinstance(obj, dict):
        return {key: _clean_non_finite(value) for key, value in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean_non_finite(value) for value in obj]
    return obj


def ingest_tool_results(state: Mapping[str, Any], messages: Sequence[ToolMessage]) -> dict[str, Any]:
    """Build one merged update from newly returned tool results.

    Candidate-owned results are accepted only for an existing candidate whose ticker
    matches the result. Invalid ownership is recorded as an error receipt and never
    falls back into global state.

    Args:
        state: Current accumulated investigation state.
        messages: New ToolMessages, including parallel results.

    Returns:
        Durable state update containing routed data and audit receipts.
    """
    raw_candidates = state.get("candidates") or {}
    candidates = {key: (value.to_dict() if hasattr(value, "to_dict") else dict(value)) for key, value in raw_candidates.items()} if isinstance(raw_candidates, Mapping) else {}
    update: dict[str, Any] = {
        "evidence": list(state.get("evidence", ())), "contradictions": list(state.get("contradictions", ())),
        "sec_corpora": list(state.get("sec_corpora", ())), "searches_performed": list(state.get("searches_performed", ())),
        "candidates": candidates, "candidate_leads": list(state.get("candidate_leads", ())),
        "comparisons": list(state.get("comparisons", ())), "source_records": list(state.get("source_records", ())),
        "claim_records": list(state.get("claim_records", ())), "capability_outputs": dict(state.get("capability_outputs", {})),
        "research_intent": dict(state.get("research_intent", {})), "ticker": state.get("ticker", ""),
        "company": state.get("company"), "cik": state.get("cik"),
    }
    confidences = [float(state["confidence"])] if isinstance(state.get("confidence"), (int, float)) and not isinstance(state.get("confidence"), bool) else []
    for message in messages:
        payload, parse_error = _parse_payload(message.content)
        status = _result_status(payload, parse_error)
        ownership_error = _candidate_ownership_error(update, message.name or "", payload) if status == "ok" else None
        if ownership_error:
            status = "error"
        update["searches_performed"].append(_build_receipt(message, payload, status, parse_error or ownership_error))
        if status not in _ERROR_STATUSES:
            _route_success(update, message.name or "", payload, confidences)
    if confidences:
        update["confidence"] = min(confidences)
    return update


def _parse_payload(content: Any) -> tuple[dict[str, Any], str | None]:
    """Parse one ToolMessage payload as a JSON object."""
    if not isinstance(content, str):
        return {}, "tool result content is not a JSON string"
    try:
        value = json.loads(content)
    except (TypeError, json.JSONDecodeError) as exc:
        return {}, f"invalid JSON: {exc.msg if isinstance(exc, json.JSONDecodeError) else exc}"
    return (value, None) if isinstance(value, dict) else ({}, "tool result JSON must be an object")


def _result_status(payload: Mapping[str, Any], parse_error: str | None) -> str:
    """Normalize payload status into a stable receipt status."""
    if parse_error:
        return "error"
    status = str(payload.get("status", "ok")).lower()
    return status if status in _ERROR_STATUSES else "ok"


def _build_receipt(message: ToolMessage, payload: Mapping[str, Any], status: str, error: str | None) -> dict[str, Any]:
    """Create an auditable compact receipt with returned routing identity."""
    receipt = {"tool": message.name or "unknown", "tool_call_id": message.tool_call_id, "status": status}
    routing = {key: payload.get(key) for key in ("candidate_id", "ticker", "cik", "corpus_id") if payload.get(key) is not None}
    if routing:
        receipt["routing"] = routing
    detail = error or (payload.get("message") if status in _ERROR_STATUSES else None)
    if detail:
        receipt["error"] = str(detail)
    if status == "error" and payload.get("code"):
        receipt["code"] = str(payload["code"])
    return receipt


def _candidate_ownership_error(update: Mapping[str, Any], tool_name: str, payload: Mapping[str, Any]) -> str | None:
    """Validate candidate identity before accepting company-specific output."""
    candidate_id = payload.get("candidate_id")
    is_multi_candidate = bool((update.get("research_intent") or {}).get("requires_candidate_workspaces"))
    if tool_name not in _CANDIDATE_SCOPED_TOOLS:
        return None
    if not is_multi_candidate and not candidate_id:
        return None
    if not candidate_id:
        return f"{tool_name} requires candidate_id for multi-candidate research"
    candidate = (update.get("candidates") or {}).get(str(candidate_id))
    if not isinstance(candidate, Mapping):
        return f"unknown candidate_id: {candidate_id}"
    payload_ticker = str(payload.get("ticker") or "").upper().strip()
    candidate_ticker = str(candidate.get("ticker") or "").upper().strip()
    if payload_ticker and candidate_ticker and payload_ticker != candidate_ticker:
        return f"candidate ticker mismatch: {candidate_ticker} != {payload_ticker}"
    return None


def _candidate(update: dict[str, Any], payload: Mapping[str, Any]) -> dict[str, Any] | None:
    """Return the validated candidate workspace for a payload, when present."""
    candidate_id = payload.get("candidate_id")
    return update["candidates"].get(str(candidate_id)) if candidate_id else None


def _route_success(update: dict[str, Any], tool_name: str, payload: Mapping[str, Any], confidences: list[float]) -> None:
    """Route one validated successful tool payload into its owning workspace."""
    clean = _clean_non_finite(dict(payload))
    ticker = str(payload.get("ticker") or "").upper().strip()
    candidate = _candidate(update, payload)
    multi_candidate = bool((update.get("research_intent") or {}).get("requires_candidate_workspaces"))
    if tool_name == "register_candidate":
        candidate_id = str(payload.get("candidate_id") or f"cand_{ticker.lower()}")
        if not ticker:
            return
        existing = update["candidates"].setdefault(candidate_id, {"candidate_id": candidate_id, "ticker": ticker, "company": str(payload.get("company") or ""), "sec_corpora": [], "evidence": [], "contradictions": [], "fact_cards": [], "status": "discovered"})
        existing["ticker"] = ticker
        existing["company"] = str(payload.get("company") or existing.get("company") or "")
        return
    if tool_name == "compare_candidates":
        c_ids = payload.get("candidate_ids") or []
        metrics = payload.get("metrics")
        from app.agent.screening import build_candidate_comparisons
        cards = build_candidate_comparisons(update["candidates"], c_ids, metrics)
        if cards:
            for card in cards:
                _append_unique_mapping(update["comparisons"], card)
        else:
            _append_unique_mapping(update["comparisons"], clean)
        return
    if tool_name in _CANDIDATE_SCOPED_TOOLS and candidate is not None:
        _route_candidate_tool(candidate, tool_name, clean, confidences)
        return
    if tool_name in _CANDIDATE_SCOPED_TOOLS and multi_candidate:
        return
    if tool_name == "get_market_data":
        update["market_context"] = clean
        if ticker and not update["ticker"]:
            update["ticker"] = ticker
    elif tool_name == "get_sec_financials":
        update["sec_financials"] = clean
    elif tool_name == "get_company_research":
        update["consensus_snapshot"] = clean
    elif tool_name == "list_sec_filings":
        update["cik"] = _payload_cik(clean) or update.get("cik")
    elif tool_name == "pull_sec_filings":
        corpus = clean.get("corpus")
        if isinstance(corpus, Mapping) and corpus.get("corpus_id"):
            _append_unique(update["sec_corpora"], str(corpus["corpus_id"]))
            update["cik"] = str(corpus.get("cik") or update.get("cik") or "") or None
    elif tool_name == "verify_sec_claim":
        verification = clean.get("verification")
        if isinstance(verification, Mapping):
            _ingest_verification(update, verification, confidences)
    elif tool_name == "get_macro_context":
        update.setdefault("capability_outputs", {})["macro_context"] = clean
    elif tool_name == "get_ownership_and_insider_activity":
        update.setdefault("capability_outputs", {})["insider_activity"] = clean
    elif tool_name in {"search_sec_evidence", "read_sec_evidence"}:
        update.setdefault("capability_outputs", {}).setdefault(tool_name, []).append(clean)
    elif tool_name in {"search_articles", "search_social", "search_web", "read_article", "read_document"}:
        _record_source_payload(update, tool_name, clean)


def _route_candidate_tool(candidate: dict[str, Any], tool_name: str, payload: Mapping[str, Any], confidences: list[float]) -> None:
    """Write a company-specific payload only to its validated candidate workspace."""
    if tool_name == "get_market_data":
        candidate["market_context"] = dict(payload)
    elif tool_name == "get_sec_financials":
        candidate["sec_financials"] = dict(payload)
    elif tool_name == "get_company_research":
        candidate["consensus_snapshot"] = dict(payload)
    elif tool_name == "list_sec_filings":
        candidate["cik"] = _payload_cik(payload) or candidate.get("cik")
    elif tool_name == "pull_sec_filings":
        corpus = payload.get("corpus")
        if isinstance(corpus, Mapping) and corpus.get("corpus_id"):
            _append_unique(candidate.setdefault("sec_corpora", []), str(corpus["corpus_id"]))
            if corpus.get("cik"):
                candidate["cik"] = str(corpus["cik"])
    elif tool_name == "verify_sec_claim" and isinstance(payload.get("verification"), Mapping):
        _ingest_verification(candidate, payload["verification"], confidences)
    elif tool_name == "get_ownership_and_insider_activity":
        candidate["insider_activity"] = dict(payload)
    elif tool_name == "read_document":
        candidate.setdefault("articles", []).append(dict(payload))
    elif tool_name in {"search_sec_evidence", "read_sec_evidence"}:
        candidate.setdefault("sec_evidence_excerpts", []).append(dict(payload))


def _payload_cik(payload: Mapping[str, Any]) -> str | None:
    """Extract a CIK from a filing-list payload."""
    if payload.get("cik"):
        return str(payload["cik"])
    filings = payload.get("filings")
    if isinstance(filings, list) and filings and isinstance(filings[0], Mapping) and filings[0].get("cik"):
        return str(filings[0]["cik"])
    return None


def _record_source_payload(update: dict[str, Any], tool_name: str, payload: Mapping[str, Any]) -> None:
    """Persist discovery/read outputs as generic source records."""
    items = [payload] if tool_name in {"read_article", "read_document"} else payload.get("articles") or payload.get("results") or payload.get("posts") or []
    if not isinstance(items, list):
        return
    for item in items:
        if not isinstance(item, Mapping):
            continue
        url = item.get("url") or item.get("source_url")
        record = {"tool": tool_name, "url": url, "title": item.get("title"), "published_at": item.get("published_at") or item.get("published"), "provider": payload.get("provider"), "status": "read" if tool_name in {"read_article", "read_document"} else "discovered"}
        if url and not any(existing.get("url") == url for existing in update["source_records"]):
            update["source_records"].append(record)

    # If read_document discovered new document/PDF links on the page, harvest them into source_records
    for doc in payload.get("discovered_documents", []) if isinstance(payload.get("discovered_documents"), list) else []:
        if isinstance(doc, Mapping) and doc.get("url"):
            d_url = doc["url"]
            if not any(existing.get("url") == d_url for existing in update["source_records"]):
                update["source_records"].append({
                    "tool": "read_document_discovery",
                    "url": d_url,
                    "title": doc.get("title") or "Discovered Document",
                    "published_at": None,
                    "provider": "document_link_harvest",
                    "status": "discovered",
                })


def _ingest_verification(update: dict[str, Any], verification: Mapping[str, Any], confidences: list[float]) -> None:
    """Merge grounded SEC verification into one owning evidence container."""
    for item in verification.get("evidence_for", ()):
        if isinstance(item, Mapping):
            update.setdefault("evidence", []).append({"claim": verification.get("claim"), "verdict": verification.get("verdict"), **dict(item)})
    for item in verification.get("evidence_against", ()):
        if isinstance(item, Mapping):
            update.setdefault("contradictions", []).append({"claim": verification.get("claim"), "verdict": verification.get("verdict"), **dict(item)})
    confidence = verification.get("confidence")
    if isinstance(confidence, (int, float)) and not isinstance(confidence, bool) and 0 <= float(confidence) <= 1:
        confidences.append(float(confidence))


def _append_unique(values: list[str], value: str) -> None:
    """Append a value once while preserving collection order."""
    if value not in values:
        values.append(value)


def _append_unique_mapping(values: list[dict[str, Any]], value: Mapping[str, Any]) -> None:
    """Append a mapping once using value equality."""
    normalized = dict(value)
    if normalized not in values:
        values.append(normalized)
