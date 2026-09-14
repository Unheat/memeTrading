"""Deterministically ingest LangChain tool results into investigation state.

This module is locally written; it contains no copied or adapted donor code.
"""
from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from langchain_core.messages import ToolMessage

_ERROR_STATUSES = frozenset({"error", "duplicate_suppressed"})


def ingest_tool_results(
    state: Mapping[str, Any], messages: Sequence[ToolMessage]
) -> dict[str, Any]:
    """Build one merged state update from newly returned tool messages.

    Args:
        state: Current investigation state whose accumulated list fields must be preserved.
        messages: Newly returned LangChain tool messages, including parallel results.

    Returns:
        One update containing routed structured results and compact execution receipts.
    """
    update: dict[str, Any] = {
        "evidence": list(state.get("evidence", ())),
        "contradictions": list(state.get("contradictions", ())),
        "sec_corpora": list(state.get("sec_corpora", ())),
        "searches_performed": list(state.get("searches_performed", ())),
    }
    prior_confidence = state.get("confidence")
    verification_confidences: list[float] = (
        [float(prior_confidence)]
        if isinstance(prior_confidence, (int, float)) and not isinstance(prior_confidence, bool)
        else []
    )

    for message in messages:
        payload, parse_error = _parse_payload(message.content)
        status = _result_status(payload, parse_error)
        update["searches_performed"].append(
            _build_receipt(message, payload, status, parse_error)
        )
        if status in _ERROR_STATUSES:
            continue
        _route_success(update, message.name or "", payload, verification_confidences)

    if verification_confidences:
        update["confidence"] = min(verification_confidences)
    return update


def _parse_payload(content: Any) -> tuple[dict[str, Any], str | None]:
    """Parse one tool message content value as a JSON object.

    Args:
        content: Raw ToolMessage content, normally a JSON string.

    Returns:
        Parsed object and no error, or an empty object and a concise parse error.
    """
    if not isinstance(content, str):
        return {}, "tool result content is not a JSON string"
    try:
        value = json.loads(content)
    except (TypeError, json.JSONDecodeError) as exc:
        return {}, f"invalid JSON: {exc.msg if isinstance(exc, json.JSONDecodeError) else exc}"
    if not isinstance(value, dict):
        return {}, "tool result JSON must be an object"
    return value, None


def _result_status(payload: Mapping[str, Any], parse_error: str | None) -> str:
    """Normalize a parsed tool result into receipt status.

    Args:
        payload: Parsed tool result object.
        parse_error: Parsing failure, when present.

    Returns:
        ``ok``, ``error``, or ``duplicate_suppressed``.
    """
    if parse_error:
        return "error"
    status = str(payload.get("status", "ok")).lower()
    return status if status in _ERROR_STATUSES else "ok"


def _build_receipt(
    message: ToolMessage,
    payload: Mapping[str, Any],
    status: str,
    parse_error: str | None,
) -> dict[str, Any]:
    """Create a compact audit receipt for one tool execution.

    Args:
        message: Source LangChain tool message.
        payload: Parsed result object, possibly empty after parse failure.
        status: Normalized execution status.
        parse_error: Parsing failure, when present.

    Returns:
        Compact receipt retaining tool identity, call identity, status, and failure detail.
    """
    receipt = {
        "tool": message.name or "unknown",
        "tool_call_id": message.tool_call_id,
        "status": status,
    }
    error = parse_error or payload.get("message") if status in _ERROR_STATUSES else None
    if error:
        receipt["error"] = str(error)
    if status == "error" and payload.get("code"):
        receipt["code"] = str(payload["code"])
    return receipt


def _route_success(
    update: dict[str, Any],
    tool_name: str,
    payload: Mapping[str, Any],
    verification_confidences: list[float],
) -> None:
    """Route one successful payload according to its ToolMessage tool name.

    Args:
        update: Mutable merged state update under construction.
        tool_name: Name of the tool that produced the result.
        payload: Parsed successful result object.
        verification_confidences: Confidence values collected in this ingestion batch.

    Returns:
        None; ``update`` and confidence collection are modified in place.
    """
    if tool_name == "get_market_data":
        update["market_context"] = dict(payload)
    elif tool_name == "get_company_research":
        update["consensus_snapshot"] = dict(payload)
    elif tool_name == "pull_sec_filings":
        corpus = payload.get("corpus")
        if isinstance(corpus, Mapping) and corpus.get("corpus_id"):
            _append_unique(update["sec_corpora"], str(corpus["corpus_id"]))
    elif tool_name == "verify_sec_claim":
        verification = payload.get("verification")
        if isinstance(verification, Mapping):
            _ingest_verification(update, verification, verification_confidences)


def _ingest_verification(
    update: dict[str, Any],
    verification: Mapping[str, Any],
    verification_confidences: list[float],
) -> None:
    """Merge grounded SEC verification evidence without promoting failures.

    Args:
        update: Mutable merged state update under construction.
        verification: Successful SEC verification object.
        verification_confidences: Confidence values collected in this ingestion batch.

    Returns:
        None; evidence, contradictions, and valid confidence are added in place.
    """
    claim = verification.get("claim")
    verdict = verification.get("verdict")
    for item in verification.get("evidence_for", ()):
        if isinstance(item, Mapping):
            update["evidence"].append({"claim": claim, "verdict": verdict, **dict(item)})
    for item in verification.get("evidence_against", ()):
        if isinstance(item, Mapping):
            update["contradictions"].append(
                {"claim": claim, "verdict": verdict, **dict(item)}
            )
    confidence = verification.get("confidence")
    if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
        if 0.0 <= float(confidence) <= 1.0:
            verification_confidences.append(float(confidence))


def _append_unique(values: list[str], value: str) -> None:
    """Append a string only when it is not already present.

    Args:
        values: Existing ordered string collection.
        value: Candidate string to append.

    Returns:
        None; ``values`` is modified in place when needed.
    """
    if value not in values:
        values.append(value)
