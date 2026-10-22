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
    altman_z_score: dict[str, Any] = Field(default_factory=dict)
    dupont_analysis: dict[str, Any] = Field(default_factory=dict)
    economic_value_spread: dict[str, Any] = Field(default_factory=dict)
    working_capital: dict[str, Any] = Field(default_factory=dict)
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

CHANNEL_TIERS = Literal[
    "tier_1_physical_core",
    "tier_2_distribution",
    "tier_3_developer",
    "tier_4_public",
]
OBSERVATION_GRADES = Literal[
    "grade_a_hard_metric",
    "grade_b_action",
    "grade_c_soft",
    "grade_d_rumor",
]

TIER_WEIGHTS: dict[str, float] = {
    "tier_1_physical_core": 1.00,
    "tier_2_distribution": 0.60,
    "tier_3_developer": 0.30,
    "tier_4_public": 0.05,
}

GRADE_WEIGHTS: dict[str, float] = {
    "grade_a_hard_metric": 1.00,
    "grade_b_action": 0.70,
    "grade_c_soft": 0.30,
    "grade_d_rumor": 0.05,
}


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
    tier: CHANNEL_TIERS = "tier_2_distribution"
    grade: OBSERVATION_GRADES = "grade_b_action"
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
            "tier": self.tier,
            "grade": self.grade,
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
    weighted_bull_score: float = 0.0
    weighted_bear_score: float = 0.0
    net_channel_momentum: float = 0.0
    channel_implied_growth: float | None = None
    channel_verdict: Literal[
        "CHANNEL_ACCELERATION",
        "CHANNEL_BREAKDOWN",
        "MIXED_CHANNEL",
        "INSUFFICIENT_CHANNEL_DATA",
        "SUSPECTED_PHANTOM_INVENTORY_HOARDING",
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
            "weighted_bull_score": self.weighted_bull_score,
            "weighted_bear_score": self.weighted_bear_score,
            "net_channel_momentum": self.net_channel_momentum,
            "channel_implied_growth": self.channel_implied_growth,
            "channel_verdict": self.channel_verdict,
            "synthesis_summary": self.synthesis_summary,
        }


class MacroDirective(BaseModel):
    """Institutional top-down macroeconomic regime and sector allocation directive."""

    model_config = ConfigDict(extra="allow")

    monetary_regime: str = "NEUTRAL"
    yield_curve_regime: str = "FLAT"
    fed_funds_rate: float | None = None
    treasury_10y_yield: float | None = None
    yield_spread_10y_2y: float | None = None
    favored_sectors: list[str] = Field(default_factory=list)
    unfavored_sectors: list[str] = Field(default_factory=list)
    cio_macro_summary: str = ""
    status: Literal["available", "insufficient_data"] = "insufficient_data"

    def to_dict(self) -> dict[str, Any]:
        """Serialize for state storage."""
        return {
            "monetary_regime": self.monetary_regime,
            "yield_curve_regime": self.yield_curve_regime,
            "fed_funds_rate": self.fed_funds_rate,
            "treasury_10y_yield": self.treasury_10y_yield,
            "yield_spread_10y_2y": self.yield_spread_10y_2y,
            "favored_sectors": list(self.favored_sectors),
            "unfavored_sectors": list(self.unfavored_sectors),
            "cio_macro_summary": self.cio_macro_summary,
            "status": self.status,
        }


# --- Specialist & Committee Structured Output Schemas ---

ForensicVerdict = Literal[
    "CLEAN_INVESTMENT_GRADE",
    "QUALIFIED_NORMALIZED_ADJUSTMENT",
    "SUSPICIOUS_EARNINGS_DISTORTION",
    "FATAL_ACCOUNTING_RED_FLAG",
]

class ForensicAuditOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    forensic_verdict: ForensicVerdict = Field(
        default="QUALIFIED_NORMALIZED_ADJUSTMENT",
        description="Overall audit verdict on financial health and earnings credibility",
    )
    beneish_m_score_risk: Literal["CLEAN", "ELEVATED", "MANIPULATION_RISK"] = Field(
        default="CLEAN",
        description="Beneish M-Score manipulation risk assessment",
    )
    sloan_accrual_quality: Literal["HIGH_QUALITY_CASH", "NORMAL_BAND", "LOW_QUALITY_ACCRUALS"] = Field(
        default="NORMAL_BAND",
        description="Sloan accrual earnings quality assessment",
    )
    sbc_dilution_burden: Literal["LOW", "MODERATE", "SEVERE_DISTORTION"] = Field(
        default="MODERATE",
        description="Stock-based compensation dilution impact",
    )
    leverage_solvency_risk: Literal["LOW", "MODERATE", "EXCESSIVE_LEVERAGE"] = Field(
        default="LOW",
        description="Debt service and leverage risk",
    )
    audit_summary: str = Field(default="", description="Summary of forensic accounting audit findings")
    key_accounting_flags: list[str] = Field(default_factory=list)


MoatRating = Literal["WIDE", "NARROW", "NONE"]
MoatSource = Literal[
    "NETWORK_EFFECTS",
    "SWITCHING_COSTS",
    "COST_ADVANTAGE",
    "INTANGIBLE_ASSETS",
    "EFFICIENT_SCALE",
    "NONE",
]

class MoatAnalysisOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    moat_rating: MoatRating = Field(default="NARROW", description="Economic moat rating: WIDE, NARROW, or NONE")
    durability_score: float = Field(default=5.0, ge=1.0, le=10.0, description="Durability score from 1.0 to 10.0")
    primary_moat_source: MoatSource = Field(default="NONE", description="Primary competitive barrier source")
    moat_summary: str = Field(default="", description="Summary of competitive advantages and moats")
    switching_costs_evidence: str = Field(default="")
    pricing_power_evidence: str = Field(default="")


class SectorAnalysisOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    sector_thesis: str = Field(default="", description="Sector positioning and competitive environment thesis")
    gross_margin_durability: Literal["EXPANDING", "STABLE", "COMPRESSING", "VULNERABLE"] = Field(
        default="STABLE", description="Gross margin durability assessment",
    )
    customer_concentration_risk: Literal["LOW", "MODERATE", "HIGH"] = Field(
        default="LOW", description="Customer concentration risk assessment",
    )
    book_to_bill_visibility: Literal["ACCELERATING", "STEADY", "DECELERATING", "OPAQUE", "STRONG", "MODERATE", "WEAK"] = Field(
        default="STEADY", description="Demand visibility assessment",
    )
    unit_cost_curve_advantage: str = Field(default="")
    key_industry_drivers: list[str] = Field(default_factory=list)


class ThematicAnalysisOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    thematic_tailwinds: Literal[
        "STRONG_SECULAR",
        "MODERATE_SECULAR",
        "CYCLICAL_PEAK",
        "COMMODITIZED_CAPEX_TRAP",
        "SECULAR_HEADWIND",
    ] = Field(default="MODERATE_SECULAR", description="Macro secular tailwind classification")
    secular_capex_wave_phase: str = Field(default="", description="Phase in secular capex wave")
    bottleneck_monopoly_score: int = Field(default=5, ge=1, le=10, description="Monopoly pricing power score (1-10)")
    thematic_summary: str = Field(default="", description="Summary of macro value-chain positioning")
    key_thematic_drivers: list[str] = Field(default_factory=list)


class BullAdvocateOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    catalysts: list[str] = Field(default_factory=list, description="Top structural operating leverage catalysts")
    operating_leverage_drivers: list[str] = Field(default_factory=list, description="Underappreciated unit-economic drivers")
    revenue_cagr_delta_bps: float | None = Field(default=None, description="Revenue CAGR upside delta in basis points")
    operating_margin_delta_bps: float | None = Field(default=None, description="Operating margin expansion delta in basis points")
    bull_target_price: float | str | None = Field(default=None, description="Upside price target derived from fundamental driver deltas")
    bull_thesis_summary: str = Field(default="", description="Institutional investment thesis")
    invalidation_conditions: list[str] = Field(default_factory=list, description="Falsifiable invalidation conditions")


class AdversarialAttackOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    falsifiable_objections: list[str] = Field(default_factory=list, description="Structural flaws or accounting/operational vulnerabilities")
    numeric_kill_criteria: list[str] = Field(default_factory=list, description="Numeric kill triggers with threshold metrics")
    revenue_cagr_delta_bps: float | None = Field(default=None, description="Downside revenue growth penalty in basis points")
    operating_margin_delta_bps: float | None = Field(default=None, description="Operating margin compression penalty in basis points")
    bear_floor_price: float | str | None = Field(default=None, description="Realistic downcycle floor price")
    bear_thesis_summary: str = Field(default="", description="Concise short-seller thesis summary")


def parse_llm_json_block(content: Any) -> dict[str, Any]:
    """Parse a model response into a JSON object without brittle string slicing.

    Deterministic validation utility: handles raw JSON, markdown-wrapped JSON (```json ... ```),
    or JSON embedded within conversational preamble.

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
    if not clean:
        raise ValueError("model content is empty")

    # 1. Try direct parse
    try:
        parsed = json.loads(clean)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # 2. Extract within markdown code fences if present
    if "```" in clean:
        parts = clean.split("```")
        for part in parts[1::2]:
            sub = part.strip()
            if sub.lower().startswith("json"):
                sub = sub[4:].strip()
            try:
                parsed = json.loads(sub)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                continue

    # 3. Outermost bracket search
    first_brace = clean.find("{")
    last_brace = clean.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        sub = clean[first_brace : last_brace + 1].strip()
        try:
            parsed = json.loads(sub)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    raise ValueError("no valid JSON object found in model content")
    return parsed
