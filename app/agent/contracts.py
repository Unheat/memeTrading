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


class FinancialSnapshot(BaseModel):
    """Audited financial snapshot for valuation modeling."""

    model_config = ConfigDict(extra="allow")

    ticker: str
    as_of_period: str | None = None
    revenue: float | None = None
    operating_income: float | None = None
    net_income: float | None = None
    cash_from_operations: float | None = None
    capex: float | None = None
    free_cash_flow: float | None = None
    cash_and_equivalents: float | None = None
    total_debt: float | None = None
    net_cash: float | None = None
    shares_diluted: float | None = None
    gross_margin_pct: float | None = None
    operating_margin_pct: float | None = None


class ForensicReport(BaseModel):
    """Deterministic forensic accounting and earnings quality report."""

    model_config = ConfigDict(extra="allow")

    status: Literal["ok", "partial", "inconclusive", "unavailable"] = "ok"
    period: str | None = None
    verdict: str = "QUALIFIED_NORMALIZED_ADJUSTMENT"
    beneish_m_score: dict[str, Any] = Field(default_factory=dict)
    sloan_accruals: dict[str, Any] = Field(default_factory=dict)
    sbc_dilution: dict[str, Any] = Field(default_factory=dict)
    leverage: dict[str, Any] = Field(default_factory=dict)
    red_flags: list[str] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    source: str = "sec_financials"
    reason: str | None = None


class BullCase(BaseModel):
    """Institutional Bull case advocate artifact."""

    model_config = ConfigDict(extra="allow")

    ticker: str
    catalysts: tuple[str, ...] = Field(default_factory=tuple)
    operating_leverage_drivers: tuple[str, ...] = Field(default_factory=tuple)
    bull_target_price: float | None = None
    bull_thesis_summary: str = ""
    invalidation_conditions: tuple[str, ...] = Field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for state storage."""
        return {
            "ticker": self.ticker,
            "catalysts": list(self.catalysts),
            "operating_leverage_drivers": list(self.operating_leverage_drivers),
            "bull_target_price": self.bull_target_price,
            "bull_thesis_summary": self.bull_thesis_summary,
            "invalidation_conditions": list(self.invalidation_conditions),
        }


class BearCase(BaseModel):
    """Hostile short-seller adversarial red team artifact."""

    model_config = ConfigDict(extra="allow")

    ticker: str
    falsifiable_objections: tuple[str, ...] = Field(default_factory=tuple)
    numeric_kill_criteria: tuple[str, ...] = Field(default_factory=tuple)
    bear_floor_price: float | None = None
    bear_thesis_summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize for state storage."""
        return {
            "ticker": self.ticker,
            "falsifiable_objections": list(self.falsifiable_objections),
            "numeric_kill_criteria": list(self.numeric_kill_criteria),
            "bear_floor_price": self.bear_floor_price,
            "bear_thesis_summary": self.bear_thesis_summary,
        }


class ValuationModel(BaseModel):
    """Deterministic Reverse DCF and quant valuation artifact."""

    model_config = ConfigDict(extra="allow")

    status: str = "ok"
    ticker: str
    fair_value: float | None = None
    fair_value_range: dict[str, float] = Field(default_factory=dict)
    implied_fcf_growth_rate: float | None = None
    reward_to_risk_ratio: float | None = None
    reproducibility: str = "unverified"
    scenarios: dict[str, Any] = Field(default_factory=dict)


class RiskRegister(BaseModel):
    """Falsifiable thesis breakers and monitoring criteria."""

    model_config = ConfigDict(extra="allow")

    ticker: str
    kill_criteria: list[str] = Field(default_factory=list)
    bear_floor: float | None = None
    max_loss_budget_pct: float = 15.0

