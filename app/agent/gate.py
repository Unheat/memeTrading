"""Deterministic evidence gates for research claims and investment decisions.

Adapted outcome semantics from reference/ai-hedge-fund/hedge_fund/signals/llm_agent.py:54-95,164-172.
Only local evidence checks are implemented; no donor signal architecture is used.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

REQUIRED_RECEIPT_TOOLS = frozenset({"get_market_data", "pull_sec_filings"})
SEC_FINANCIAL_STATUSES = frozenset({"ok", "ok_foreign_issuer_unstructured"})
SEC_FORMS = frozenset({"10-K", "10-Q", "20-F", "6-K", "8-K", "S-1", "F-1"})


def has_candidate_sec_evidence(candidate: Mapping[str, Any]) -> bool:
    """Return whether a candidate has deterministic, candidate-scoped SEC coverage.

    Args:
        candidate: Candidate-isolated workspace.

    Returns:
        True when SEC financial extraction, a local corpus, or SEC-attributed evidence exists.
    """
    sec_financials = candidate.get("sec_financials")
    if isinstance(sec_financials, Mapping):
        status = str(sec_financials.get("status") or "")
        if status in SEC_FINANCIAL_STATUSES or bool(sec_financials.get("periods")):
            return True
    if candidate.get("sec_corpora"):
        return True
    for investigation in candidate.get("sec_investigations") or ():
        if isinstance(investigation, Mapping) and str(investigation.get("status") or "") == "ok":
            return True
    for item in candidate.get("evidence") or ():
        if not isinstance(item, Mapping):
            continue
        form = str(item.get("form") or "").upper()
        source = str(item.get("source") or "").upper()
        source_url = str(item.get("source_url") or "").lower()
        if form in SEC_FORMS or source == "SEC" or "sec.gov" in source_url:
            return True
    return False


def _candidate_is_evidence_backed(candidate: Mapping[str, Any]) -> bool:
    """Return whether one registered candidate has independent research evidence.

    Args:
        candidate: Candidate-isolated workspace.

    Returns:
        True only when market and primary/SEC evidence are available, or candidate was explicitly vetoed.
    """
    if candidate.get("status") in {"vetoed", "rejected", "screened_out"} or candidate.get("veto_reason"):
        return True
    return bool(candidate.get("market_context")) and has_candidate_sec_evidence(candidate)


def evaluate_research_completeness(state: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate evidence against the prompt-directed research intent.

    Args:
        state: Accumulated investigation state after tool collection.

    Returns:
        A truthful completion result. Ranking requests never receive allocation output.
    """
    intent = state.get("research_intent") or {}
    requested_count = intent.get("requested_ranking_count")
    candidates = state.get("candidates") or {}

    if candidates:
        backed = [candidate for candidate in candidates.values() if isinstance(candidate, Mapping) and _candidate_is_evidence_backed(candidate)]
        target_count = requested_count or len(candidates)
        missing = []
        if len(backed) < target_count:
            missing.append(
                f"Requested {target_count} evidence-backed candidates; collected {len(backed)}."
            )
        if not state.get("comparisons") and len(candidates) > 1:
            missing.append("A normalized candidate comparison is missing.")
        return {
            "passed": not missing,
            "status": "completed" if not missing else "research_incomplete",
            "decision": "RANKING_COMPLETE" if not missing else "RANKING_INCOMPLETE",
            "allocation_pct": 0.0,
            "requested_ranking_count": target_count,
            "evidence_backed_candidates": len(backed),
            "missing_evidence": missing,
        }

    if not intent.get("requested_position_decision"):
        source_count = len(state.get("source_records", []))
        has_evidence = source_count > 0 or bool(state.get("evidence")) or bool(state.get("market_context")) or bool(state.get("searches_performed"))
        return {
            "passed": has_evidence,
            "status": "completed" if has_evidence else "research_incomplete",
            "decision": "RESEARCH_COMPLETE" if has_evidence else "RESEARCH_INCOMPLETE",
            "allocation_pct": None,
            "missing_evidence": [] if has_evidence else ["No usable sources or evidence were collected."],
        }

    missing: list[str] = []
    ticker = str(state.get("ticker") or "").strip().upper()
    if not ticker:
        missing.append("verified ticker identity is missing")
    if not state.get("company") and not state.get("cik"):
        missing.append("verified company identity is missing")
    if not state.get("cik"):
        missing.append("SEC CIK identity is missing")
    market = state.get("market_context")
    if not isinstance(market, Mapping):
        missing.append("current market data is unavailable")
    else:
        quote = market.get("quote") if isinstance(market.get("quote"), Mapping) else {}
        if quote.get("price") is None and quote.get("value") is None:
            missing.append("current price is unavailable")
        if not market.get("currency") and not quote.get("currency"):
            missing.append("market-data currency is unavailable")
        if not market.get("as_of") and not quote.get("as_of"):
            missing.append("market-data as-of time is unavailable")
        if not isinstance(market.get("addv_20d"), Mapping) or market["addv_20d"].get("value") is None:
            missing.append("20-day ADDV/liquidity is unavailable")
    if not state.get("sec_corpora") and not state.get("evidence"):
        missing.append("primary SEC evidence is unavailable")
    successful_tools = {str(receipt.get("tool")) for receipt in state.get("searches_performed", ()) if isinstance(receipt, Mapping) and receipt.get("status") == "ok"}
    for tool in sorted(REQUIRED_RECEIPT_TOOLS - successful_tools):
        missing.append(f"required {tool} receipt is missing")
    return {
        "passed": not missing,
        "status": "ready_for_review" if not missing else "insufficient_evidence",
        "decision": None if not missing else "NO_POSITION",
        "allocation_pct": None if not missing else 0.0,
        "missing_evidence": missing,
    }


def evaluate_accounting_gate(state: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate G2 from the deterministic forensic report."""
    report = state.get("forensic_report") or {}
    if report.get("status") != "available":
        return {"passed": False, "status": "validation_required", "reason": report.get("reason", "accounting report unavailable")}
    verdict = str(report.get("verdict") or "").upper()
    if "FATAL" in verdict or "RED_FLAG" in verdict:
        return {"passed": False, "status": "validation_required", "reason": f"Fatal accounting red flag: {report.get('verdict')}"}
    return {"passed": True, "status": "ready_for_valuation", "reason": None}


def evaluate_valuation_gate(state: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate G3 reproducibility for the deterministic quant report."""
    report = state.get("quant_report") or {}
    verification = report.get("reproducibility") or {}
    verdict = verification.get("verdict")
    if not verdict and verification.get("status") == "ok":
        verdict = (verification.get("result") or {}).get("verdict")
    passed = report.get("status") == "available" and str(verdict or "").lower() == "pass"
    return {"passed": passed, "status": "ready_for_debate" if passed else "validation_required", "reason": None if passed else report.get("reason", "valuation is not reproducible")}


def evaluate_asymmetry_gate(state: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate G4 only from deterministic, source-backed valuation values."""
    valuation = ((state.get("quant_report") or {}).get("valuation") or {})
    risk = valuation.get("asymmetric_risk_reward") or {}
    passed = bool(risk.get("qualifies_3_to_1"))
    return {"passed": passed, "status": "ready_for_committee" if passed else "fails_asymmetric_hurdle", "reason": None if passed else "source-backed low/base valuation does not clear 3:1"}


PUBLICATION_BLOCKED_RESEARCH_STATUSES = frozenset({
    "in_progress", "research_incomplete", "insufficient_evidence", "validation_required", "failed",
})


def evaluate_publication_readiness(
    state: Mapping[str, Any],
    citation_cards: Sequence[Any] | None = None,
) -> dict[str, Any]:
    """Determine whether a case may create outward-facing article or video artifacts.

    Args:
        state: Completed investigation state with deterministic gate outcomes.
        citation_cards: Server-owned citation cards created from admitted state evidence.

    Returns:
        JSON-safe readiness result with allowed artifact kinds and blocking reasons.
    """
    reasons: list[str] = []
    research_status = str(state.get("status") or "in_progress")
    if research_status in PUBLICATION_BLOCKED_RESEARCH_STATUSES:
        reasons.append(f"research status is {research_status}")

    cards = list(citation_cards or ())
    if not cards:
        reasons.append("no server-owned citation cards are available")

    intent = state.get("research_intent") or {}
    if intent.get("requested_position_decision"):
        for gate_name in ("evidence_gate", "accounting_gate", "valuation_gate"):
            gate = state.get(gate_name) or {}
            if not isinstance(gate, Mapping) or not gate.get("passed", False):
                reasons.append(f"{gate_name} did not pass")

    for report_name in ("bull_report", "adversarial_report"):
        report = state.get(report_name)
        status = report.get("status") if isinstance(report, Mapping) else getattr(report, "status", None)
        if status and status != "available":
            reasons.append(f"{report_name} is {status}")

    passed = not reasons
    return {
        "passed": passed,
        "status": "publishable" if passed else "blocked",
        "reasons": reasons,
        "allowed_artifacts": ["article", "video", "publish"] if passed else [],
    }
