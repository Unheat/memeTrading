"""Deterministic evidence gates for research claims and investment decisions.

Adapted outcome semantics from reference/ai-hedge-fund/hedge_fund/signals/llm_agent.py:54-95,164-172.
Only local evidence checks are implemented; no donor signal architecture is used.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

REQUIRED_RECEIPT_TOOLS = frozenset({"get_market_data", "pull_sec_filings"})


def _candidate_is_evidence_backed(candidate: Mapping[str, Any]) -> bool:
    """Return whether one registered candidate has independent research evidence.

    Args:
        candidate: Candidate-isolated workspace.

    Returns:
        True only when market and primary/SEC evidence are available.
    """
    return bool(candidate.get("market_context")) and bool(
        candidate.get("sec_financials") or candidate.get("sec_corpora") or candidate.get("evidence")
    )


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
    if requested_count:
        backed = [candidate for candidate in candidates.values() if isinstance(candidate, Mapping) and _candidate_is_evidence_backed(candidate)]
        missing = []
        if len(backed) < requested_count:
            missing.append(
                f"Requested {requested_count} evidence-backed candidates; collected {len(backed)}."
            )
        if not state.get("comparisons"):
            missing.append("A normalized candidate comparison is missing.")
        return {
            "passed": not missing,
            "status": "completed" if not missing else "research_incomplete",
            "decision": "RANKING_COMPLETE" if not missing else "RANKING_INCOMPLETE",
            "allocation_pct": 0.0,
            "requested_ranking_count": requested_count,
            "evidence_backed_candidates": len(backed),
            "missing_evidence": missing,
        }

    if not intent.get("requested_position_decision"):
        source_count = len(state.get("source_records", []))
        has_evidence = source_count > 0 or bool(state.get("evidence")) or bool(state.get("market_context"))
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
    return {"passed": True, "status": "ready_for_valuation", "reason": None}


def evaluate_valuation_gate(state: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate G3 reproducibility for the deterministic quant report."""
    report = state.get("quant_report") or {}
    verification = report.get("reproducibility") or {}
    result = verification.get("result") if verification.get("status") == "ok" else {}
    passed = report.get("status") == "available" and result.get("verdict") == "pass"
    return {"passed": passed, "status": "ready_for_debate" if passed else "validation_required", "reason": None if passed else report.get("reason", "valuation is not reproducible")}


def evaluate_asymmetry_gate(state: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate G4 only from deterministic, source-backed valuation values."""
    valuation = ((state.get("quant_report") or {}).get("valuation") or {})
    risk = valuation.get("asymmetric_risk_reward") or {}
    passed = bool(risk.get("qualifies_3_to_1"))
    return {"passed": passed, "status": "ready_for_committee" if passed else "validation_required", "reason": None if passed else "source-backed low/base valuation does not clear 3:1"}
