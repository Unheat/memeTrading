"""Closed-world grounded synthesis and claim-to-evidence validation boundary.

Enforces that model synthesis assertions are bound to server-owned, case-local evidence.
This module is locally written; it contains no copied or adapted donor code.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
import hashlib
import logging
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.agent.ledger import ClaimRecord, EvidenceLink, SourceDocument, SourceExcerpt

logger = logging.getLogger(__name__)

ClaimType = Literal[
    "financial_metric",
    "operational_fact",
    "expectation_gap",
    "thesis_risk",
    "macro_trend",
    "governance",
]


class GroundedClaim(BaseModel):
    """One structured factual claim or inference proposed by model reasoning."""

    model_config = ConfigDict(extra="forbid")

    claim_id: str = Field(description="Unique stable claim identifier, e.g. claim_1")
    statement: str = Field(description="Factual assertion or inference statement", max_length=1000)
    claim_type: ClaimType = Field(description="Taxonomic category of this claim")
    evidence_link_ids: list[str] = Field(
        default_factory=list,
        description="Opaque excerpt IDs or fact IDs from the supplied evidence packet supporting this claim",
        max_length=10,
    )
    is_inference: bool = Field(
        default=False,
        description="True if this is an analytical inference rather than an audited primary quote or metric",
    )
    limitations: list[str] = Field(
        default_factory=list,
        description="Explicit caveats or data limitations affecting this claim",
        max_length=5,
    )


class GroundedSynthesis(BaseModel):
    """Structured research synthesis bounded to the supplied case-local evidence packet."""

    model_config = ConfigDict(extra="forbid")

    executive_claims: list[GroundedClaim] = Field(default_factory=list, max_length=10)
    findings: list[GroundedClaim] = Field(default_factory=list, max_length=20)
    limitations: list[str] = Field(default_factory=list, max_length=10)


@dataclass(frozen=True)
class PacketEvidenceItem:
    """Opaque evidence reference presented to the model during synthesis."""

    item_id: str
    source_type: str
    fact_summary: str
    candidate_id: str | None = None
    ticker: str | None = None
    locator: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize evidence item for LLM prompt ingestion."""
        return asdict(self)


def build_evidence_packet(
    state: Mapping[str, Any],
    candidate_id: str | None = None,
) -> dict[str, Any]:
    """Compile an exact, case/candidate-scoped evidence packet of opaque IDs and verified facts.

    The model receives only opaque identifiers and factual statements. It never receives
    arbitrary raw URLs to invent or modify provenance metadata.

    Args:
        state: Accumulated investigation state.
        candidate_id: Optional candidate ID to scope evidence to one company.

    Returns:
        Dictionary mapping item_id to PacketEvidenceItem dictionaries.
    """
    items: dict[str, dict[str, Any]] = {}

    def _register(
        item_id: str,
        source_type: str,
        fact: str,
        cand_id: str | None = None,
        ticker: str | None = None,
        locator: str | None = None,
    ) -> None:
        if not item_id or not fact:
            return
        if candidate_id and cand_id and cand_id != candidate_id:
            return
        items[item_id] = PacketEvidenceItem(
            item_id=item_id,
            source_type=source_type,
            fact_summary=fact.strip(),
            candidate_id=cand_id,
            ticker=ticker,
            locator=locator,
        ).to_dict()

    # 1. FactCards from state and candidate workspaces
    global_facts = state.get("fact_cards") or ()
    for fc in global_facts:
        if isinstance(fc, Mapping):
            fid = str(fc.get("fact_id") or "")
            metric = fc.get("metric_key") or "fact"
            val = fc.get("value")
            unit = fc.get("unit") or ""
            stmt = fc.get("quote") or f"{metric}: {val} {unit}".strip()
            _register(
                item_id=fid,
                source_type="FactCard",
                fact=stmt,
                cand_id=fc.get("candidate_id"),
                ticker=fc.get("ticker"),
                locator=fc.get("accession") or fc.get("period"),
            )

    candidates = state.get("candidates") or {}
    if isinstance(candidates, Mapping):
        for cid, cand in candidates.items():
            if not isinstance(cand, Mapping):
                continue
            if candidate_id and cid != candidate_id:
                continue
            c_ticker = str(cand.get("ticker") or "")
            for fc in cand.get("fact_cards") or ():
                if isinstance(fc, Mapping):
                    fid = str(fc.get("fact_id") or "")
                    stmt = fc.get("quote") or f"{fc.get('metric_key')}: {fc.get('value')}"
                    _register(
                        item_id=fid,
                        source_type="FactCard",
                        fact=stmt,
                        cand_id=cid,
                        ticker=c_ticker,
                        locator=fc.get("accession") or fc.get("period"),
                    )

            # Candidate evidence quotes
            for ev in cand.get("evidence") or ():
                if isinstance(ev, Mapping) and ev.get("quote"):
                    eid = str(ev.get("excerpt_id") or f"exc_{hashlib.sha256(str(ev.get('quote')).encode('utf-8')).hexdigest()[:12]}")
                    _register(
                        item_id=eid,
                        source_type=str(ev.get("form") or ev.get("source") or "SEC"),
                        fact=str(ev["quote"]),
                        cand_id=cid,
                        ticker=c_ticker,
                        locator=ev.get("accession") or ev.get("source_url"),
                    )

    # 2. Global state evidence items
    for ev in state.get("evidence") or ():
        if isinstance(ev, Mapping) and ev.get("quote"):
            eid = str(ev.get("excerpt_id") or f"exc_{hashlib.sha256(str(ev.get('quote')).encode('utf-8')).hexdigest()[:12]}")
            _register(
                item_id=eid,
                source_type=str(ev.get("form") or ev.get("source") or "Evidence"),
                fact=str(ev["quote"]),
                cand_id=ev.get("candidate_id"),
                ticker=state.get("ticker"),
                locator=ev.get("accession") or ev.get("source_url"),
            )

    # 3. Citation cards if built
    from app.agent.media import build_source_registry
    try:
        cards = build_source_registry(state)  # type: ignore[arg-type]
        for card in cards:
            cid = f"card_{card.index}"
            for fact in card.facts:
                _register(
                    item_id=f"{cid}_fact_{hashlib.sha256(fact.encode('utf-8')).hexdigest()[:8]}",
                    source_type=card.source_type,
                    fact=fact,
                    locator=card.accession or card.url,
                )
            for quote in card.quotes:
                _register(
                    item_id=f"{cid}_quote_{hashlib.sha256(quote.encode('utf-8')).hexdigest()[:8]}",
                    source_type=card.source_type,
                    fact=quote,
                    locator=card.accession or card.url,
                )
    except Exception as exc:
        logger.debug("Citation cards not integrated into evidence packet: %s", exc)

    return {
        "candidate_id": candidate_id,
        "items": items,
        "count": len(items),
    }


def validate_grounded_synthesis(
    synthesis: GroundedSynthesis,
    packet: Mapping[str, Any],
    allowed_candidate_id: str | None = None,
) -> dict[str, Any]:
    """Deterministically validate model-proposed claims against the supplied evidence packet.

    Args:
        synthesis: Parsed GroundedSynthesis structured output from the LLM.
        packet: Server-owned evidence packet provided to the model.
        allowed_candidate_id: Candidate ID that all cited evidence must belong to.

    Returns:
        Dict with 'passed' (bool), 'errors' (list[str]), 'claim_records' (list[dict]),
        and 'evidence_links' (list[dict]).
    """
    errors: list[str] = []
    items: dict[str, Any] = packet.get("items") or {}

    validated_claims: list[ClaimRecord] = []
    validated_links: list[EvidenceLink] = []

    all_claims: list[GroundedClaim] = list(synthesis.executive_claims) + list(synthesis.findings)

    for claim in all_claims:
        # Factual assertions require at least one supporting evidence link
        if not claim.is_inference and not claim.evidence_link_ids:
            errors.append(f"Factual claim '{claim.claim_id}' lacks supporting evidence links: '{claim.statement[:60]}'")
            continue

        claim_link_ids: list[str] = []
        for eid in claim.evidence_link_ids:
            if eid not in items:
                errors.append(f"Claim '{claim.claim_id}' cites unknown evidence link ID '{eid}'")
                continue

            item = items[eid]
            item_cand_id = item.get("candidate_id")
            if allowed_candidate_id and item_cand_id and item_cand_id != allowed_candidate_id:
                errors.append(
                    f"Claim '{claim.claim_id}' cross-cites candidate {item_cand_id} while evaluating {allowed_candidate_id}"
                )
                continue

            link_id = f"link_{hashlib.sha256((claim.claim_id + eid).encode('utf-8')).hexdigest()[:12]}"
            link = EvidenceLink(
                evidence_link_id=link_id,
                claim_id=claim.claim_id,
                excerpt_id=eid,
                relation="supports",
            )
            validated_links.append(link)
            claim_link_ids.append(link_id)

        rec = ClaimRecord(
            claim_id=claim.claim_id,
            statement=claim.statement,
            claim_type=claim.claim_type,
            status="supported" if claim_link_ids or claim.is_inference else "unsupported",
            subject_id=allowed_candidate_id,
            evidence_link_ids=tuple(claim_link_ids),
            limitations=tuple(claim.limitations),
        )
        validated_claims.append(rec)

    passed = len(errors) == 0
    return {
        "passed": passed,
        "errors": errors,
        "claim_records": [c.to_dict() for c in validated_claims] if passed else [],
        "evidence_links": [l.to_dict() for l in validated_links] if passed else [],
    }


def materialize_evidence_records(state: dict[str, Any]) -> None:
    """Ensure all admitted evidence items possess immutable excerpt and source identities.

    Args:
        state: State dictionary to mutate in-place.
    """
    source_records = state.setdefault("source_records", [])
    evidence_items = state.setdefault("evidence", [])

    for ev in evidence_items:
        if not isinstance(ev, dict):
            continue
        url = str(ev.get("source_url") or "https://www.sec.gov")
        quote = str(ev.get("quote") or "")
        if not ev.get("excerpt_id") and quote:
            ev["excerpt_id"] = f"exc_{hashlib.sha256((url + quote[:200]).encode('utf-8')).hexdigest()[:12]}"

        src_id = f"src_{hashlib.sha256(url.encode('utf-8')).hexdigest()[:12]}"
        ev["source_id"] = src_id

        if not any(s.get("source_id") == src_id or s.get("url") == url for s in source_records):
            source_records.append({
                "source_id": src_id,
                "url": url,
                "title": ev.get("title") or f"SEC Filing {ev.get('form', '')}".strip(),
                "status": "read",
                "content_sha256": hashlib.sha256(quote.encode("utf-8")).hexdigest(),
                "candidate_id": ev.get("candidate_id"),
            })
