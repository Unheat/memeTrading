"""Typed contracts shared across model-visible tool boundaries.

This module is locally written. It defines the normalized result status envelope
that prevents provider degradation from being silently admitted as evidence.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ToolStatus = Literal[
    "ok",
    "partial",
    "ok_foreign_issuer_unstructured",
    "not_applicable",
    "unavailable",
    "paywalled",
    "invalid_input",
    "entity_conflict",
    "duplicate_suppressed",
    "error",
]

ADMISSIBLE_EVIDENCE_STATUSES = frozenset({"ok", "partial", "ok_foreign_issuer_unstructured"})
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
    """Institutional Bull case advocate artifact.

    ``status`` is honest: ``available`` only when the model produced a valid numeric
    target; ``degraded`` when fallbacks fired; ``unavailable`` when unparseable.
    """

    model_config = ConfigDict(extra="allow")

    ticker: str
    catalysts: tuple[str, ...] = Field(default_factory=tuple)
    operating_leverage_drivers: tuple[str, ...] = Field(default_factory=tuple)
    bull_target_price: float | None = None
    bull_thesis_summary: str = ""
    invalidation_conditions: tuple[str, ...] = Field(default_factory=tuple)
    status: str = "available"
    degradation_reasons: tuple[str, ...] = Field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for state storage."""
        return {
            "ticker": self.ticker,
            "catalysts": list(self.catalysts),
            "operating_leverage_drivers": list(self.operating_leverage_drivers),
            "bull_target_price": self.bull_target_price,
            "bull_thesis_summary": self.bull_thesis_summary,
            "invalidation_conditions": list(self.invalidation_conditions),
            "status": self.status,
            "degradation_reasons": list(self.degradation_reasons),
        }


class BearCase(BaseModel):
    """Hostile short-seller adversarial red team artifact.

    ``status`` is honest: ``available`` when a numeric bear floor parsed; ``degraded``
    when field-level fallbacks fired; ``unavailable`` when the model was unparseable.
    """

    model_config = ConfigDict(extra="allow")

    ticker: str
    falsifiable_objections: tuple[str, ...] = Field(default_factory=tuple)
    numeric_kill_criteria: tuple[str, ...] = Field(default_factory=tuple)
    bear_floor_price: float | None = None
    bear_thesis_summary: str = ""
    status: str = "available"
    degradation_reasons: tuple[str, ...] = Field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for state storage."""
        return {
            "ticker": self.ticker,
            "falsifiable_objections": list(self.falsifiable_objections),
            "numeric_kill_criteria": list(self.numeric_kill_criteria),
            "bear_floor_price": self.bear_floor_price,
            "bear_thesis_summary": self.bear_thesis_summary,
            "status": self.status,
            "degradation_reasons": list(self.degradation_reasons),
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


CHANNEL_CHECK_TYPES = Literal[
    "distributor_inventory",
    "spot_pricing",
    "developer_telemetry",
    "sysadmin_operator_feedback",
    "merchant_adoption",
    "customer_churn",
    "retail_shelf_check",
]
CHANNEL_IMPLICATIONS = Literal["bullish_inflection", "neutral", "bearish_inflection"]


class ChannelCheckReceipt(BaseModel):
    """One auditable ground-truth channel observation (Fisher scuttlebutt receipt).

    Conforms to the Mosaic Theory: individually non-material, publicly observable
    facts recorded with source, metric, and verbatim evidence so an investment
    committee can audit every inference. Vague sentiment scores are deliberately
    excluded — each receipt maps to an observable metric.
    """

    model_config = ConfigDict(extra="allow")

    receipt_id: str
    channel_type: CHANNEL_CHECK_TYPES
    source_url_or_channel: str
    target_ticker: str
    observed_metric: str
    observed_value: float | str
    baseline_value: float | str | None = None
    implication: CHANNEL_IMPLICATIONS = "neutral"
    quote_or_evidence: str = ""
    observed_at_utc: str | None = None

    @field_validator("target_ticker")
    @classmethod
    def _normalize_ticker(cls, value: str) -> str:
        """Uppercase and strip the issuer ticker for deterministic ownership."""
        return value.strip().upper()

    def to_dict(self) -> dict[str, Any]:
        """Serialize for state storage."""
        return {
            "receipt_id": self.receipt_id,
            "channel_type": self.channel_type,
            "source_url_or_channel": self.source_url_or_channel,
            "target_ticker": self.target_ticker,
            "observed_metric": self.observed_metric,
            "observed_value": self.observed_value,
            "baseline_value": self.baseline_value,
            "implication": self.implication,
            "quote_or_evidence": self.quote_or_evidence,
            "observed_at_utc": self.observed_at_utc,
        }


class ChannelCheckReport(BaseModel):
    """Synthesized scuttlebutt assessment for one candidate workspace.

    Counts and verdicts are deterministic classifications of receipts; the model
    may author only ``synthesis_summary``. ``channel_implied_growth`` stays None
    until a deterministic transaction-to-KPI calibration exists upstream.
    """

    model_config = ConfigDict(extra="allow")

    ticker: str
    status: Literal["available", "insufficient_data", "degraded"] = "insufficient_data"
    receipts: list[dict[str, Any]] = Field(default_factory=list)
    receipts_count: int = 0
    bullish_count: int = 0
    bearish_count: int = 0
    discordant_signals: int = 0
    channel_implied_growth: float | None = None
    channel_verdict: Literal[
        "CHANNEL_ACCELERATION",
        "CHANNEL_BREAKDOWN",
        "MIXED_CHANNEL",
        "INSUFFICIENT_CHANNEL_DATA",
    ] = "INSUFFICIENT_CHANNEL_DATA"
    synthesis_summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize for state storage."""
        return {
            "ticker": self.ticker,
            "status": self.status,
            "receipts": list(self.receipts),
            "receipts_count": self.receipts_count,
            "bullish_count": self.bullish_count,
            "bearish_count": self.bearish_count,
            "discordant_signals": self.discordant_signals,
            "channel_implied_growth": self.channel_implied_growth,
            "channel_verdict": self.channel_verdict,
            "synthesis_summary": self.synthesis_summary,
        }



def parse_llm_json_block(content: Any) -> dict[str, Any]:
    """Parse a model response into a JSON object, stripping markdown fences.

    Deterministic validation utility: it performs no intent inference — it either
    returns the parsed mapping or raises so callers can degrade honestly.

    Args:
        content: Raw model response content (string expected).

    Returns:
        Parsed JSON mapping.

    Raises:
        ValueError: If the content is not a string or is not valid JSON.
    """
    import json

    if not isinstance(content, str):
        raise ValueError("model content is not a string")
    clean = content.strip()
    if "```json" in clean:
        clean = clean.split("```json")[1].split("```")[0].strip()
    elif clean.startswith("```"):
        clean = clean.strip("`")
        if clean.startswith("json"):
            clean = clean[4:].strip()
    parsed = json.loads(clean)
    if not isinstance(parsed, dict):
        raise ValueError("model JSON is not an object")
    return parsed
