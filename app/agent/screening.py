"""Multi-candidate screening, candidate isolation, and fact card models.

Adapted from reference/investment-research/schemas/candidate-list.schema.json:1-45
and reference/investment-research/contracts/screener.yaml:1-25.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping


@dataclass(frozen=True)
class CandidateLead:
    """Discovery lead surfaced by news, articles, social signals, or web search."""

    ticker: str
    company: str
    source_url: str | None = None
    source_type: str = "discovery"
    inclusion_reason: str = ""
    exposure_type: str = "pure_play"
    discovered_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        """Serialize lead into dictionary."""
        return asdict(self)


@dataclass(frozen=True)
class ScreenCandidate:
    """Registered candidate company with verified or resolving identity."""

    candidate_id: str
    ticker: str
    company: str
    cik: str | None = None
    exchange: str | None = None
    status: str = "discovered"  # discovered | identity_verified | partial | review_ready | rejected

    def to_dict(self) -> dict[str, Any]:
        """Serialize candidate into dictionary."""
        return asdict(self)


@dataclass
class CandidateResearchState:
    """Isolated research workspace for one candidate company."""

    candidate_id: str
    ticker: str
    company: str
    cik: str | None = None
    market_context: dict[str, Any] | None = None
    consensus_snapshot: dict[str, Any] | None = None
    sec_financials: dict[str, Any] | None = None
    sec_corpora: list[str] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    contradictions: list[dict[str, Any]] = field(default_factory=list)
    fact_cards: list[dict[str, Any]] = field(default_factory=list)
    articles: list[dict[str, Any]] = field(default_factory=list)
    social_signals: list[dict[str, Any]] = field(default_factory=list)
    status: str = "discovered"
    rejection_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert candidate state to a serializable dictionary."""
        return {
            "candidate_id": self.candidate_id,
            "ticker": self.ticker,
            "company": self.company,
            "cik": self.cik,
            "market_context": self.market_context,
            "consensus_snapshot": self.consensus_snapshot,
            "sec_financials": self.sec_financials,
            "sec_corpora": list(self.sec_corpora),
            "evidence": list(self.evidence),
            "contradictions": list(self.contradictions),
            "fact_cards": list(self.fact_cards),
            "articles": list(self.articles),
            "social_signals": list(self.social_signals),
            "status": self.status,
            "rejection_reason": self.rejection_reason,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CandidateResearchState:
        """Construct candidate state from dictionary."""
        return cls(
            candidate_id=str(data.get("candidate_id") or ""),
            ticker=str(data.get("ticker") or "").upper().strip(),
            company=str(data.get("company") or ""),
            cik=str(data.get("cik")) if data.get("cik") else None,
            market_context=dict(data["market_context"]) if isinstance(data.get("market_context"), Mapping) else None,
            consensus_snapshot=dict(data["consensus_snapshot"]) if isinstance(data.get("consensus_snapshot"), Mapping) else None,
            sec_financials=dict(data["sec_financials"]) if isinstance(data.get("sec_financials"), Mapping) else None,
            sec_corpora=list(data.get("sec_corpora") or []),
            evidence=list(data.get("evidence") or []),
            contradictions=list(data.get("contradictions") or []),
            fact_cards=list(data.get("fact_cards") or []),
            articles=list(data.get("articles") or []),
            social_signals=list(data.get("social_signals") or []),
            status=str(data.get("status") or "discovered"),
            rejection_reason=str(data.get("rejection_reason")) if data.get("rejection_reason") else None,
        )


@dataclass(frozen=True)
class FactCard:
    """Atomic, cited unit of financial truth for one company."""

    fact_id: str
    candidate_id: str
    ticker: str
    metric_key: str
    period: str
    value: float | None
    unit: str = "USD"
    quote: str = ""
    source_url: str = ""
    accession: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize fact card into dictionary."""
        return asdict(self)


@dataclass(frozen=True)
class ComparisonCard:
    """Normalized cross-company comparison on a single metric."""

    comparison_id: str
    metric_key: str
    period_basis: str
    candidate_values: dict[str, Any]  # ticker -> {value, quote, source_url}
    comparability: str = "comparable"  # comparable | period_mismatch | currency_mismatch | unavailable
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize comparison card into dictionary."""
        return asdict(self)


def build_candidate_comparisons(
    candidates: Mapping[str, Any],
    candidate_ids: list[str],
    metrics: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Build normalized side-by-side comparison cards from registered candidate workspaces.

    Args:
        candidates: Mapping of candidate_id to candidate workspace dictionary or object.
        candidate_ids: Ordered list of candidate IDs to compare.
        metrics: List of financial metric keys to extract.

    Returns:
        List of serialized ComparisonCard dictionaries.
    """
    target_metrics = metrics or [
        "price", "pe_ratio", "gross_margin", "operating_margin", "revenue", "net_cash", "capex"
    ]
    cards: list[dict[str, Any]] = []

    for metric in target_metrics:
        cand_values: dict[str, Any] = {}
        periods_seen: set[str] = set()

        for c_id in candidate_ids:
            cand_raw = candidates.get(c_id)
            if not cand_raw:
                continue
            cand = cand_raw.to_dict() if hasattr(cand_raw, "to_dict") else dict(cand_raw)
            ticker = str(cand.get("ticker") or c_id).upper()
            mkt = cand.get("market_context") or {}
            sec = cand.get("sec_financials") or {}
            periods = sec.get("periods") or []
            latest_period = periods[0] if periods else "latest"

            val = None
            if metric == "price":
                val = (mkt.get("quote") or {}).get("price") or (mkt.get("quote") or {}).get("value")
            elif metric == "pe_ratio":
                fund = mkt.get("fundamentals") or {}
                val = fund.get("pe_ratio") or fund.get("trailing_pe")
            elif metric in ("gross_margin", "gross_margin_pct"):
                val = (sec.get("gross_margin_pct") or {}).get(latest_period)
                if latest_period != "latest":
                    periods_seen.add(latest_period)
            elif metric in ("operating_margin", "operating_margin_pct"):
                val = (sec.get("operating_margin_pct") or {}).get(latest_period)
                if latest_period != "latest":
                    periods_seen.add(latest_period)
            elif metric == "revenue":
                val = (sec.get("revenue") or {}).get(latest_period)
                if latest_period != "latest":
                    periods_seen.add(latest_period)
            elif metric == "net_cash":
                val = (sec.get("net_cash") or {}).get(latest_period)
                if latest_period != "latest":
                    periods_seen.add(latest_period)
            elif metric == "capex":
                val = (sec.get("capex") or {}).get(latest_period)
                if latest_period != "latest":
                    periods_seen.add(latest_period)

            cand_values[ticker] = {
                "value": val,
                "period": latest_period,
                "candidate_id": c_id,
            }

        comparability = "comparable"
        if len(periods_seen) > 1:
            comparability = "period_mismatch"
        elif not any(cv.get("value") is not None for cv in cand_values.values()):
            comparability = "unavailable"

        card = ComparisonCard(
            comparison_id=f"comp_{metric}",
            metric_key=metric,
            period_basis="latest" if not periods_seen else next(iter(periods_seen)),
            candidate_values=cand_values,
            comparability=comparability,
            notes=f"Comparison across {len(cand_values)} candidates for {metric}.",
        )
        cards.append(card.to_dict())

    return cards
