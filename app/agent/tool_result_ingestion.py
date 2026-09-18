"""Deterministically ingest tool results into universal research state.

This module is locally written; it contains no copied or adapted donor code.
"""
from __future__ import annotations

import json
import logging
import math
from collections.abc import Mapping, Sequence
from typing import Any

from langchain_core.messages import ToolMessage

from app.agent.contracts import ADMISSIBLE_EVIDENCE_STATUSES, ToolResultEnvelope

logger = logging.getLogger(__name__)

_NON_ROUTABLE_STATUSES = frozenset({
    "not_applicable", "unavailable", "paywalled", "invalid_input",
    "entity_conflict", "duplicate_suppressed", "error",
})
_CANDIDATE_SCOPED_TOOLS = frozenset({
    "get_market_data", "get_sec_financials", "get_company_research", "list_sec_filings",
    "pull_sec_filings", "verify_sec_claim", "search_sec_evidence", "read_sec_evidence",
    "get_ownership_and_insider_activity", "conduct_candidate_diligence", "evaluate_valuation",
    "investigate_sec",
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
        if parse_error:
            envelope = ToolResultEnvelope(status="error", payload=payload, reason=parse_error)
        else:
            tool_name = message.name or ""
            if tool_name in _CANDIDATE_SCOPED_TOOLS and not payload.get("candidate_id"):
                ticker = str(payload.get("ticker") or "").upper().strip()
                if ticker:
                    matched_ids = [
                        candidate_id
                        for candidate_id, candidate in candidates.items()
                        if isinstance(candidate, Mapping) and str(candidate.get("ticker") or "").upper().strip() == ticker
                    ]
                    if len(matched_ids) == 1:
                        payload = {**payload, "candidate_id": matched_ids[0]}
                        logger.info(
                            "pipeline.candidate_id_resolved tool=%s ticker=%s candidate_id=%s",
                            tool_name, ticker, matched_ids[0],
                        )
            envelope = ToolResultEnvelope.from_payload(payload)

        ownership_error = (
            _candidate_ownership_error(update, message.name or "", envelope.payload)
            if envelope.status in ADMISSIBLE_EVIDENCE_STATUSES
            else None
        )
        if ownership_error:
            envelope = envelope.model_copy(update={
                "status": "error",
                "code": "entity_conflict",
                "reason": ownership_error,
            })

        receipt = _build_receipt(message, envelope)
        update["searches_performed"].append(receipt)
        logger.info(
            "pipeline.tool_receipt tool=%s status=%s candidate_id=%s ticker=%s code=%s",
            receipt["tool"], envelope.status, envelope.candidate_id, envelope.ticker, envelope.code,
        )
        if envelope.status in ADMISSIBLE_EVIDENCE_STATUSES:
            _route_success(
                update,
                message.name or "",
                envelope.payload,
                confidences,
                allow_partial=envelope.status == "partial",
            )
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


def _build_receipt(message: ToolMessage, envelope: ToolResultEnvelope) -> dict[str, Any]:
    """Create an auditable compact receipt preserving normalized tool status."""
    receipt = {
        "tool": message.name or "unknown",
        "tool_call_id": message.tool_call_id,
        "status": envelope.status,
    }
    routing = {
        key: value for key, value in {
            "candidate_id": envelope.candidate_id,
            "ticker": envelope.ticker,
            "cik": envelope.cik,
            "corpus_id": envelope.corpus_id,
        }.items() if value is not None
    }
    if routing:
        receipt["routing"] = routing
    if envelope.reason and envelope.status in _NON_ROUTABLE_STATUSES | {"partial"}:
        receipt["error"] = str(envelope.reason)
    if envelope.code:
        receipt["code"] = str(envelope.code)
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
    corpus = payload.get("corpus") if isinstance(payload.get("corpus"), Mapping) else {}
    payload_ticker = str(payload.get("ticker") or corpus.get("ticker") or "").upper().strip()
    candidate_ticker = str(candidate.get("ticker") or "").upper().strip()
    if payload_ticker and candidate_ticker and payload_ticker != candidate_ticker:
        return f"candidate ticker mismatch: {candidate_ticker} != {payload_ticker}"

    payload_cik = str(_payload_cik(payload) or "").lstrip("0")
    candidate_cik = str(candidate.get("cik") or "").lstrip("0")
    if payload_cik and candidate_cik and payload_cik != candidate_cik:
        return f"candidate CIK mismatch: {candidate_cik} != {payload_cik}"

    corpus = payload.get("corpus")
    corpus_id = payload.get("corpus_id") or (corpus.get("corpus_id") if isinstance(corpus, Mapping) else None)
    allowed_corpora = set(str(item) for item in candidate.get("sec_corpora", ()) if item)
    if corpus_id and allowed_corpora and str(corpus_id) not in allowed_corpora:
        return f"candidate corpus mismatch: {corpus_id} is not owned by {candidate_id}"
    return None


def _candidate(update: dict[str, Any], payload: Mapping[str, Any]) -> dict[str, Any] | None:
    """Return the validated candidate workspace for a payload, when present."""
    candidate_id = payload.get("candidate_id")
    return update["candidates"].get(str(candidate_id)) if candidate_id else None


def _route_success(
    update: dict[str, Any],
    tool_name: str,
    payload: Mapping[str, Any],
    confidences: list[float],
    allow_partial: bool = False,
) -> None:
    """Route a validated tool payload while preserving partial-data limitations.

    Partial data is useful for research, but it cannot establish corpora or claim
    verification until a later complete evidence receipt confirms it.
    """
    clean = _clean_non_finite(dict(payload))
    if allow_partial:
        clean["status"] = "partial"
    ticker = str(payload.get("ticker") or "").upper().strip()
    candidate = _candidate(update, payload)
    multi_candidate = bool((update.get("research_intent") or {}).get("requires_candidate_workspaces"))
    if tool_name == "register_candidate":
        candidate_id = str(payload.get("candidate_id") or f"cand_{ticker.lower()}")
        if not ticker:
            return
        cand_status = str(payload.get("candidate_status") or payload.get("status") or "discovered")
        if cand_status == "ok":
            cand_status = str(payload.get("candidate_status") or "discovered")
        reason = str(payload.get("reason") or "")
        existing = update["candidates"].setdefault(
            candidate_id,
            {
                "candidate_id": candidate_id,
                "ticker": ticker,
                "company": str(payload.get("company") or ""),
                "sec_corpora": [],
                "evidence": [],
                "contradictions": [],
                "fact_cards": [],
                "status": cand_status,
            }
        )
        existing["ticker"] = ticker
        existing["company"] = str(payload.get("company") or existing.get("company") or "")
        existing["status"] = cand_status
        if cand_status in {"vetoed", "rejected", "screened_out"}:
            existing["veto_reason"] = reason
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
    if tool_name in {"get_sec_financials", "get_market_data"}:
        t_clean = str(ticker or payload.get("ticker") or (candidate.get("ticker") if candidate else "") or "").upper().strip()
        c_id = str(payload.get("candidate_id") or (candidate.get("candidate_id") if candidate else "") or "")
        cards = _distill_fact_cards(tool_name, clean, t_clean, c_id)
        for card in cards:
            if candidate is not None:
                _append_fact_card(candidate.setdefault("fact_cards", []), card)
            _append_fact_card(update.setdefault("fact_cards", []), card)

    if tool_name in _CANDIDATE_SCOPED_TOOLS and candidate is not None:
        _route_candidate_tool(candidate, tool_name, clean, confidences, allow_partial=allow_partial)
        if multi_candidate:
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
        if clean.get("filings") and isinstance(clean["filings"], list):
            update["sec_filings"] = list(clean["filings"])
    elif tool_name == "pull_sec_filings":
        corpus = clean.get("corpus")
        if not allow_partial and isinstance(corpus, Mapping) and corpus.get("corpus_id"):
            _append_unique(update["sec_corpora"], str(corpus["corpus_id"]))
            update["cik"] = str(corpus.get("cik") or update.get("cik") or "") or None
    elif tool_name == "verify_sec_claim":
        verification = clean.get("verification")
        if not allow_partial and isinstance(verification, Mapping):
            _ingest_verification(update, verification, confidences)
    elif tool_name == "get_macro_context":
        update.setdefault("capability_outputs", {})["macro_context"] = clean
    elif tool_name == "get_ownership_and_insider_activity":
        update.setdefault("capability_outputs", {})["insider_activity"] = clean
    elif tool_name == "conduct_candidate_diligence":
        update.setdefault("capability_outputs", {}).setdefault("diligence_dossiers", {})[ticker] = clean
    elif tool_name == "evaluate_valuation":
        update.setdefault("capability_outputs", {}).setdefault("valuations", {})[ticker] = clean
    elif tool_name == "investigate_sec":
        evidence_items = clean.get("evidence") or []
        for ev in evidence_items:
            if isinstance(ev, Mapping) and ev.get("quote"):
                ev_clean = {
                    "quote": ev.get("quote"),
                    "source": ev.get("form") or "SEC",
                    "form": ev.get("form"),
                    "filing_date": ev.get("filing_date"),
                    "source_url": ev.get("source_url"),
                    "accession": ev.get("accession"),
                    "verdict": clean.get("assessment", "CONFIRMED"),
                }
                update["evidence"].append(ev_clean)
        update.setdefault("capability_outputs", {}).setdefault("sec_investigations", []).append(clean)
    elif tool_name in {"search_sec_evidence", "read_sec_evidence"}:
        update.setdefault("capability_outputs", {}).setdefault(tool_name, []).append(clean)
    elif tool_name in {"search_articles", "search_social", "search_web", "read_article", "read_document"}:
        _record_source_payload(update, tool_name, clean)


def _append_fact_card(target: list[dict[str, Any]], card: Mapping[str, Any]) -> None:
    """Append a FactCard idempotently by unique fact_id."""
    fid = str(card.get("fact_id") or "")
    if not fid:
        return
    for existing in target:
        if str(existing.get("fact_id") or "") == fid:
            return
    target.append(dict(card))


def _distill_fact_cards(
    tool_name: str,
    payload: Mapping[str, Any],
    ticker: str,
    candidate_id: str | None = None,
) -> list[dict[str, Any]]:
    """Deterministically distill atomic, cited FactCards from tool payloads."""
    from app.agent.screening import FactCard
    import re

    cards: list[dict[str, Any]] = []
    t_clean = (ticker or str(payload.get("ticker") or "")).strip().upper()
    if not t_clean or t_clean == "UNKNOWN":
        return cards

    c_id = candidate_id or f"cand_{t_clean.lower()}"

    def _slug(p: str) -> str:
        return re.sub(r"[^a-z0-9_]+", "_", p.strip().lower())

    if tool_name == "get_sec_financials":
        periods = payload.get("periods") or ()
        metrics_to_extract = [
            ("revenue", "USD"),
            ("gross_profit", "USD"),
            ("gross_margin_pct", "ratio"),
            ("operating_income", "USD"),
            ("operating_margin_pct", "ratio"),
            ("net_income", "USD"),
            ("cash_and_equivalents", "USD"),
            ("total_debt", "USD"),
            ("net_cash", "USD"),
            ("inventory", "USD"),
            ("cash_from_operations", "USD"),
            ("capex", "USD"),
            ("fcf", "USD"),
            ("total_assets", "USD"),
            ("accounts_receivable", "USD"),
            ("current_assets", "USD"),
            ("ppe", "USD"),
            ("depreciation", "USD"),
            ("sg_and_a", "USD"),
            ("stock_based_compensation", "USD"),
            ("current_liabilities", "USD"),
        ]
        provider = str(payload.get("provider", "sec_xbrl"))
        source_url = f"https://www.sec.gov/edgar/browse/?CIK={t_clean}"

        for metric_key, unit in metrics_to_extract:
            series = payload.get(metric_key)
            if isinstance(series, Mapping):
                for p in periods:
                    val = series.get(p)
                    if val is not None:
                        try:
                            f_val = float(val)
                        except (ValueError, TypeError):
                            continue
                        cards.append(
                            FactCard(
                                fact_id=f"fact_{t_clean.lower()}_{metric_key}_{_slug(str(p))}",
                                candidate_id=c_id,
                                ticker=t_clean,
                                metric_key=metric_key,
                                period=str(p),
                                value=f_val,
                                unit=unit,
                                quote=f"SEC XBRL {metric_key} for {p}: {f_val}",
                                source_url=source_url,
                                accession=provider,
                            ).to_dict()
                        )

        # Distill TTM FCF if computed
        ttm_fcf = payload.get("ttm_fcf")
        if ttm_fcf is not None:
            try:
                f_ttm = float(ttm_fcf)
                cards.append(
                    FactCard(
                        fact_id=f"fact_{t_clean.lower()}_ttm_fcf",
                        candidate_id=c_id,
                        ticker=t_clean,
                        metric_key="ttm_fcf",
                        period="TTM",
                        value=f_ttm,
                        unit="USD",
                        quote=f"Trailing twelve months Free Cash Flow: {f_ttm}",
                        source_url=source_url,
                        accession=provider,
                    ).to_dict()
                )
            except (ValueError, TypeError):
                pass

    elif tool_name == "get_market_data":
        quote = payload.get("quote") or {}
        if isinstance(quote, Mapping):
            price = quote.get("price")
            as_of = str(quote.get("as_of", "latest"))[:10]
            if price is not None:
                try:
                    f_price = float(price)
                    cards.append(
                        FactCard(
                            fact_id=f"fact_{t_clean.lower()}_spot_price",
                            candidate_id=c_id,
                            ticker=t_clean,
                            metric_key="price",
                            period=f"SPOT-{as_of}",
                            value=f_price,
                            unit="USD",
                            quote=f"Observed market price as of {as_of}: {f_price}",
                            source_url="",
                            accession="market_quote",
                        ).to_dict()
                    )
                except (ValueError, TypeError):
                    pass

    return cards


def _route_candidate_tool(
    candidate: dict[str, Any],
    tool_name: str,
    payload: Mapping[str, Any],
    confidences: list[float],
    allow_partial: bool = False,
) -> None:
    """Write validated company-specific payloads to their owning workspace."""
    if tool_name == "get_market_data":
        candidate["market_context"] = dict(payload)
    elif tool_name == "get_sec_financials":
        candidate["sec_financials"] = dict(payload)
    elif tool_name == "get_company_research":
        candidate["consensus_snapshot"] = dict(payload)
    elif tool_name == "list_sec_filings":
        candidate["cik"] = _payload_cik(payload) or candidate.get("cik")
        if payload.get("filings") and isinstance(payload["filings"], list):
            candidate["sec_filings"] = list(payload["filings"])
    elif tool_name == "pull_sec_filings":
        corpus = payload.get("corpus")
        if not allow_partial and isinstance(corpus, Mapping) and corpus.get("corpus_id"):
            _append_unique(candidate.setdefault("sec_corpora", []), str(corpus["corpus_id"]))
            if corpus.get("cik"):
                candidate["cik"] = str(corpus["cik"])
        elif allow_partial:
            candidate.setdefault("limitations", []).append("SEC corpus pull returned partial data and was not admitted as a verified corpus.")
    elif tool_name == "verify_sec_claim" and isinstance(payload.get("verification"), Mapping):
        if not allow_partial:
            _ingest_verification(candidate, payload["verification"], confidences)
        else:
            candidate.setdefault("limitations", []).append("SEC claim verification returned partial data and was not admitted as verified evidence.")
    elif tool_name == "investigate_sec":
        evidence_items = payload.get("evidence") or []
        for ev in evidence_items:
            if isinstance(ev, Mapping) and ev.get("quote"):
                ev_clean = {
                    "quote": ev.get("quote"),
                    "source": ev.get("form") or "SEC",
                    "form": ev.get("form"),
                    "filing_date": ev.get("filing_date"),
                    "source_url": ev.get("source_url"),
                    "accession": ev.get("accession"),
                    "verdict": payload.get("assessment", "CONFIRMED"),
                }
                candidate.setdefault("evidence", []).append(ev_clean)
        candidate.setdefault("sec_investigations", []).append(dict(payload))
    elif tool_name == "get_ownership_and_insider_activity":
        candidate["insider_activity"] = dict(payload)
    elif tool_name == "read_document":
        candidate.setdefault("articles", []).append(dict(payload))
    elif tool_name in {"search_sec_evidence", "read_sec_evidence"}:
        candidate.setdefault("sec_evidence_excerpts", []).append(dict(payload))
    elif tool_name == "conduct_candidate_diligence":
        candidate["diligence_dossier"] = dict(payload)
        if not candidate.get("market_context") and payload.get("market_context"):
            candidate["market_context"] = dict(payload["market_context"])
        if not candidate.get("sec_financials") and payload.get("sec_financials"):
            candidate["sec_financials"] = dict(payload["sec_financials"])
    elif tool_name == "evaluate_valuation":
        candidate["quant_report"] = payload.get("quant_report")
        if payload.get("valuation"):
            candidate["valuation"] = dict(payload["valuation"])


def _payload_cik(payload: Mapping[str, Any]) -> str | None:
    """Extract a CIK from a filing-list payload."""
    if payload.get("cik"):
        return str(payload["cik"])
    filings = payload.get("filings")
    if isinstance(filings, list) and filings and isinstance(filings[0], Mapping) and filings[0].get("cik"):
        return str(filings[0]["cik"])
    return None


def _record_source_payload(update: dict[str, Any], tool_name: str, payload: Mapping[str, Any]) -> None:
    """Persist discovery/read outputs as generic source records and durable ledger items."""
    import hashlib
    from app.agent.ledger import SourceDocument, SourceExcerpt

    items = (
        [payload]
        if tool_name in {"read_article", "read_document"}
        else (payload.get("articles") or payload.get("results") or payload.get("records") or payload.get("posts") or [])
    )
    if not isinstance(items, list):
        return
    for item in items:
        if not isinstance(item, Mapping):
            continue
        url = item.get("url") or item.get("source_url")
        if not url:
            continue
        title = str(item.get("title") or "Discovered source")
        status = "read" if tool_name in {"read_article", "read_document"} else "discovered"
        content_text = str(item.get("text") or item.get("content") or item.get("snippet") or "")
        content_sha = hashlib.sha256(content_text.encode("utf-8")).hexdigest()

        # Build stable source ID
        src_id = f"src_{hashlib.sha256(url.encode('utf-8')).hexdigest()[:12]}"
        doc_record = {
            "source_id": src_id,
            "tool": tool_name,
            "url": str(url),
            "title": title,
            "published_at": item.get("published_at") or item.get("published"),
            "provider": payload.get("provider"),
            "status": status,
            "content_sha256": content_sha,
            "candidate_id": payload.get("candidate_id") or item.get("candidate_id"),
        }

        # Deduplicate by URL in source_records
        existing = next((s for s in update["source_records"] if s.get("url") == url), None)
        if not existing:
            update["source_records"].append(doc_record)
        elif status == "read" and existing.get("status") == "discovered":
            existing["status"] = "read"
            existing["content_sha256"] = content_sha

        # If document was read, extract source-local citation excerpt
        if tool_name in {"read_article", "read_document"} and content_text:
            excerpt_id = f"exc_{hashlib.sha256((url + content_text[:200]).encode('utf-8')).hexdigest()[:12]}"
            update.setdefault("evidence", []).append({
                "excerpt_id": excerpt_id,
                "source_id": src_id,
                "source_url": str(url),
                "title": title,
                "quote": content_text[:500],
                "candidate_id": payload.get("candidate_id"),
            })

    # If read_document discovered new document/PDF links on the page, harvest them into source_records
    for doc in payload.get("discovered_documents", []) if isinstance(payload.get("discovered_documents"), list) else []:
        if isinstance(doc, Mapping) and doc.get("url"):
            d_url = doc["url"]
            if not any(existing.get("url") == d_url for existing in update["source_records"]):
                d_src_id = f"src_{hashlib.sha256(str(d_url).encode('utf-8')).hexdigest()[:12]}"
                update["source_records"].append({
                    "source_id": d_src_id,
                    "tool": "read_document_discovery",
                    "url": str(d_url),
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
