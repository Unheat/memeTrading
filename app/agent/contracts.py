"""Typed contracts shared across model-visible tool boundaries.

This module is locally written. It defines the normalized result status envelope
that prevents provider degradation from being silently admitted as evidence.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ToolStatus = Literal[
    "ok",
    "partial",
    "not_applicable",
    "unavailable",
    "paywalled",
    "invalid_input",
    "entity_conflict",
    "duplicate_suppressed",
    "error",
]

ADMISSIBLE_EVIDENCE_STATUSES = frozenset({"ok", "partial"})
NON_EVIDENCE_STATUSES = frozenset({
    "not_applicable", "unavailable", "paywalled", "invalid_input",
    "entity_conflict", "duplicate_suppressed", "error",
})


class ToolResultEnvelope(BaseModel):
    """Validated, normalized tool result admitted by the research state.

    Args:
        status: Explicit normalized outcome category.
        payload: Tool-specific JSON object retained after validation.
        reason: Public, sanitized outcome explanation.
        code: Stable machine-readable diagnostic code.
        candidate_id: Candidate workspace owner when applicable.
        ticker: Normalized issuer ticker when applicable.
        cik: Normalized SEC issuer identity when applicable.
        corpus_id: Candidate-owned corpus identity when applicable.

    Returns:
        Typed model used before tool output is persisted or routed.
    """

    model_config = ConfigDict(extra="allow")

    status: ToolStatus
    payload: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = None
    code: str | None = None
    candidate_id: str | None = None
    ticker: str | None = None
    cik: str | None = None
    corpus_id: str | None = None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ToolResultEnvelope":
        """Normalize a raw tool JSON object without converting degradation to success."""
        raw_status = str(payload.get("status", "ok")).strip().lower()
        aliases = {
            "extraction_failed": "unavailable",
            "validation_error": "invalid_input",
            "failed": "error",
        }
        status = aliases.get(raw_status, raw_status)
        if status not in ADMISSIBLE_EVIDENCE_STATUSES | NON_EVIDENCE_STATUSES:
            return cls(
                status="invalid_input",
                payload=dict(payload),
                code="unknown_tool_status",
                reason=f"Tool returned unsupported status: {raw_status or 'empty'}.",
                candidate_id=payload.get("candidate_id"),
                ticker=payload.get("ticker"),
                cik=payload.get("cik"),
                corpus_id=payload.get("corpus_id"),
            )
        return cls(
            status=status,
            payload=dict(payload),
            reason=payload.get("reason") or payload.get("message"),
            code=payload.get("code"),
            candidate_id=payload.get("candidate_id"),
            ticker=payload.get("ticker"),
            cik=payload.get("cik"),
            corpus_id=payload.get("corpus_id"),
        )
