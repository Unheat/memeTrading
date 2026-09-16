"""Isolated candidate deep diligence sub-agent runner.

Donor provenance: adapted from LangChain Open Deep Research sub-agent spawning
and reference/investment-research parallel specialist DAG execution.
Each candidate runs with an isolated context window and returns a structured dossier.
"""
from __future__ import annotations

import logging
from typing import Any, Mapping

from app.agent.adversarial import run_adversarial_red_team
from app.agent.bull import run_bull_advocate
from app.agent.expectations import run_expectations_analyst
from app.agent.specialists import (
    run_forensic_analysis,
    run_moat_analysis,
    run_quant_analysis,
)

logger = logging.getLogger(__name__)


def run_candidate_diligence(
    ticker: str,
    candidate_id: str | None = None,
    focus_questions: list[str] | None = None,
    candidate_workspace: Mapping[str, Any] | None = None,
    model: Any | None = None,
) -> dict[str, Any]:
    """Execute an isolated deep diligence sub-agent for one company.

    Args:
        ticker: Ticker symbol (e.g. 'MSFT').
        candidate_id: Optional candidate ID.
        focus_questions: Optional specific research angles requested by supervisor.
        candidate_workspace: Existing candidate state if already collected.
        model: Model runtime for specialist LLM calls.

    Returns:
        Structured JSON dossier with valuation, Bull catalysts, and Bear kill-criteria.
    """
    clean_ticker = ticker.strip().upper()
    cid = candidate_id or f"cand_{clean_ticker.lower()}"
    ws = dict(candidate_workspace or {})

    # Build isolated synthetic state for this candidate
    cand_state: dict[str, Any] = {
        "ticker": clean_ticker,
        "company": ws.get("company"),
        "cik": ws.get("cik"),
        "market_context": ws.get("market_context"),
        "sec_financials": ws.get("sec_financials"),
        "consensus_snapshot": ws.get("consensus_snapshot"),
        "sec_corpora": ws.get("sec_corpora", []),
        "evidence": ws.get("evidence", []),
        "trigger": {"query": f"Deep diligence on {clean_ticker}", "theme": "Enterprise AI & Cloud"},
    }

    # If market context is missing, fetch it
    if not cand_state.get("market_context"):
        try:
            from app.market.market_data import get_market_data
            cand_state["market_context"] = get_market_data(clean_ticker).to_dict()
        except Exception as exc:
            logger.debug("Failed to fetch market data for %s: %s", clean_ticker, exc)

    # If SEC financials are missing, fetch them
    if not cand_state.get("sec_financials"):
        try:
            from app.sec.financials import get_sec_financials
            cand_state["sec_financials"] = get_sec_financials(clean_ticker).to_dict()
        except Exception as exc:
            logger.debug("Failed to fetch SEC financials for %s: %s", clean_ticker, exc)

    # 1. Expectations analysis
    exp_res = {}
    if model:
        try:
            exp_res = run_expectations_analyst(cand_state, model)
            cand_state.update(exp_res)
        except Exception as exc:
            logger.warning("Expectations analysis failed for %s: %s", clean_ticker, exc)

    # 2. Forensic accounting & Moat
    forensic_res = {}
    moat_res = {}
    if model:
        try:
            forensic_res = run_forensic_analysis(cand_state, model)
            cand_state.update(forensic_res)
        except Exception as exc:
            logger.warning("Forensic analysis failed for %s: %s", clean_ticker, exc)
        try:
            moat_res = run_moat_analysis(cand_state, model)
            cand_state.update(moat_res)
        except Exception as exc:
            logger.warning("Moat analysis failed for %s: %s", clean_ticker, exc)

    # 3. Deterministic Reverse DCF / Quant modeling
    quant_res = {}
    try:
        quant_res = run_quant_analysis(cand_state)
        cand_state.update(quant_res)
    except Exception as exc:
        logger.warning("Quant analysis failed for %s: %s", clean_ticker, exc)

    # 4. Air-gapped Bull Advocate
    bull_res = {}
    if model:
        try:
            bull_res = run_bull_advocate(cand_state, model)
            cand_state.update(bull_res)
        except Exception as exc:
            logger.warning("Bull advocate failed for %s: %s", clean_ticker, exc)

    # 5. Hostile Bear Red Team
    bear_res = {}
    if model:
        try:
            bear_res = run_adversarial_red_team(cand_state, model)
            cand_state.update(bear_res)
        except Exception as exc:
            logger.warning("Bear red team failed for %s: %s", clean_ticker, exc)

    # Extract clean dossier values
    bull = cand_state.get("bull_report")
    bear = cand_state.get("adversarial_report")
    quant = cand_state.get("quant_report") or {}
    val = quant.get("valuation") or {}

    dossier: dict[str, Any] = {
        "status": "ok",
        "ticker": clean_ticker,
        "candidate_id": cid,
        "company": cand_state.get("company"),
        "valuation": {
            "implied_growth_rate": val.get("implied_fcf_growth_rate"),
            "fair_value": val.get("fair_value"),
            "fair_value_range": val.get("fair_value_range"),
            "reward_to_risk_ratio": (val.get("asymmetric_risk_reward") or {}).get("reward_to_risk_ratio"),
            "reproducibility": (quant.get("reproducibility") or {}).get("verdict", "unverified"),
        },
        "bull_catalysts": list(getattr(bull, "catalysts", [])) if bull else [],
        "bull_thesis": getattr(bull, "bull_thesis_summary", ""),
        "bear_kill_triggers": list(getattr(bear, "numeric_kill_criteria", [])) if bear else [],
        "bear_thesis": getattr(bear, "bear_thesis_summary", ""),
        "bear_floor": getattr(bear, "bear_floor_price", None),
        "forensic_verdict": (cand_state.get("forensic_report") or {}).get("verdict"),
        "moat_rating": (cand_state.get("moat_report") or {}).get("analysis", {}).get("moat_rating"),
    }
    return dossier
