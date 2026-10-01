"""Isolated candidate deep diligence sub-agent runner.

Donor provenance: adapted from LangChain Open Deep Research sub-agent spawning
and reference/investment-research parallel specialist DAG execution.
Each candidate runs with an isolated context window and returns a structured dossier.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Mapping

from app.agent.adversarial import run_adversarial_red_team
from app.agent.bull import run_bull_advocate
from app.agent.expectations import run_expectations_analyst
from app.agent.specialists import (
    run_channel_check_analysis,
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
        "expectation_gap": ws.get("expectation_gap"),
        "macro_series": ws.get("macro_series"),
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

    # --- Stage 1: Independent Fundamentals (Expectations, Forensics, Moat, Channel in parallel) ---
    exp_res: dict[str, Any] = {}
    forensic_res: dict[str, Any] = {}
    moat_res: dict[str, Any] = {}
    channel_res: dict[str, Any] = {}

    if model:
        with ThreadPoolExecutor(max_workers=4) as executor:
            fut_exp = executor.submit(run_expectations_analyst, cand_state, model)
            fut_for = executor.submit(run_forensic_analysis, cand_state, model)
            fut_moat = executor.submit(run_moat_analysis, cand_state, model)
            fut_chan = executor.submit(run_channel_check_analysis, cand_state, model)

            try:
                exp_res = fut_exp.result()
            except Exception as exc:
                logger.warning("Expectations analysis failed for %s: %s", clean_ticker, exc)

            try:
                forensic_res = fut_for.result()
            except Exception as exc:
                logger.warning("Forensic analysis failed for %s: %s", clean_ticker, exc)

            try:
                moat_res = fut_moat.result()
            except Exception as exc:
                logger.warning("Moat analysis failed for %s: %s", clean_ticker, exc)

            try:
                channel_res = fut_chan.result()
            except Exception as exc:
                logger.warning("Channel check analysis failed for %s: %s", clean_ticker, exc)
    else:
        # Deterministic offline paths when model is None
        try:
            forensic_res = run_forensic_analysis(cand_state, None)
        except Exception as exc:
            logger.warning("Forensic analysis failed for %s: %s", clean_ticker, exc)
        try:
            moat_res = run_moat_analysis(cand_state, None)
        except Exception as exc:
            logger.warning("Moat analysis failed for %s: %s", clean_ticker, exc)
        try:
            channel_res = run_channel_check_analysis(cand_state, None)
        except Exception as exc:
            logger.warning("Channel check analysis failed for %s: %s", clean_ticker, exc)

    cand_state.update(exp_res)
    cand_state.update(forensic_res)
    cand_state.update(moat_res)
    cand_state.update(channel_res)

    # --- Stage 2: Quant DCF / Valuation modeling (synchronous, consuming Stage 1 expectation_gap) ---
    quant_res: dict[str, Any] = {}
    try:
        quant_res = run_quant_analysis(cand_state)
        cand_state.update(quant_res)
    except Exception as exc:
        logger.warning("Quant analysis failed for %s: %s", clean_ticker, exc)

    # --- Stage 3: Dialectical Debate (Air-gapped Bull Advocate & Bear Red Team in parallel) ---
    bull_res: dict[str, Any] = {}
    bear_res: dict[str, Any] = {}

    if model:
        with ThreadPoolExecutor(max_workers=2) as executor:
            fut_bull = executor.submit(run_bull_advocate, cand_state, model)
            fut_bear = executor.submit(run_adversarial_red_team, cand_state, model)

            try:
                bull_res = fut_bull.result()
            except Exception as exc:
                logger.warning("Bull advocate failed for %s: %s", clean_ticker, exc)

            try:
                bear_res = fut_bear.result()
            except Exception as exc:
                logger.warning("Bear red team failed for %s: %s", clean_ticker, exc)

        cand_state.update(bull_res)
        cand_state.update(bear_res)

    # Extract clean dossier values
    bull = cand_state.get("bull_report")
    bear = cand_state.get("adversarial_report")
    dossier = build_diligence_dossier(cand_state, bull, bear, cid, clean_ticker)
    return dossier


def build_diligence_dossier(
    cand_state: dict[str, Any],
    bull: Any | None,
    bear: Any | None,
    cid: str,
    clean_ticker: str,
) -> dict[str, Any]:
    """Project the diligence sub-agent's specialist outputs into the slim dossier payload.

    Args:
        cand_state: Candidate-scoped state after all specialist stages ran.
        bull: Bull advocate report object (or None).
        bear: Adversarial red team report object (or None).
        cid: Candidate workspace id.
        clean_ticker: Normalized ticker symbol.

    Returns:
        Dossier dict with the same outer keys as before plus additive completeness
        fields (bull_target_price, report statuses, full moat_report).
    """
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
        "bull_target_price": getattr(bull, "bull_target_price", None),
        "bull_report_status": getattr(bull, "status", "unavailable"),
        "bear_kill_triggers": list(getattr(bear, "numeric_kill_criteria", [])) if bear else [],
        "bear_thesis": getattr(bear, "bear_thesis_summary", ""),
        "bear_floor": getattr(bear, "bear_floor_price", None),
        "bear_report_status": getattr(bear, "status", "unavailable"),
        "forensic_verdict": (cand_state.get("forensic_report") or {}).get("verdict"),
        "moat_rating": (cand_state.get("moat_report") or {}).get("analysis", {}).get("moat_rating"),
        # Full moat report travels in the dossier so the committee deliberates on it
        # (audit 2026-09-26, Fix 5 — previously reduced to a rating string and dropped).
        "moat_report": cand_state.get("moat_report"),
        # Scuttlebutt channel telemetry (receipts + deterministic verdict) travels with
        # the dossier so the 3-way expectation arbitrage can weigh ground truth.
        "channel_check_report": cand_state.get("channel_check_report"),
        "market_context": cand_state.get("market_context"),
        "sec_financials": cand_state.get("sec_financials"),
        "expectation_gap": cand_state.get("expectation_gap"),
    }
    return dossier
