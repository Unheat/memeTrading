"""Tests for state synchronization between candidate screening, diligence, and media registry."""
from __future__ import annotations

import json
import pytest
from langchain_core.messages import ToolMessage
from app.agent.state import ResearchRequest, create_initial_state
from app.agent.tool_result_ingestion import ingest_tool_results
from app.agent.media import build_source_registry
from app.agent.bull import BullReport, BullCase
from app.agent.adversarial import AdversarialReport, BearCase


def test_diligence_financials_synchronize_with_candidate_and_media_registry():
    """Verify that audited diligence financials overwrite stale candidate screening data and propagate to citation cards."""
    req = ResearchRequest(query="Analyze GOOG", ticker="GOOG", company="Alphabet")
    state = create_initial_state(req, case_id="case_goog_sync")

    # 1. Simulate Candidate Screening tool results (stale screening data)
    screening_tool_messages = [
        ToolMessage(
            tool_call_id="call_register",
            name="register_candidate",
            content='{"status": "ok", "candidate_id": "cand_goog", "ticker": "GOOG", "company": "Alphabet"}',
        ),
        ToolMessage(
            tool_call_id="call_sec_fin_stale",
            name="get_sec_financials",
            content=(
                '{"status": "ok", "ticker": "GOOG", "periods": ["Q4 2025"], '
                '"revenue": {"Q4 2025": 113829000000.0}, '
                '"gross_margin_pct": {"Q4 2025": 0.598}, '
                '"cash_from_operations": {"Q4 2025": 3990000000.0}, '
                '"capex": {"Q4 2025": 27850000000.0}, '
                '"ttm_fcf": -22890000000.0, '
                '"candidate_id": "cand_goog"}'
            ),
        ),
    ]

    state = ingest_tool_results(state, screening_tool_messages)
    assert "cand_goog" in state["candidates"]
    # Before diligence, screening data has the old value
    assert state["candidates"]["cand_goog"]["sec_financials"]["ttm_fcf"] == -22890000000.0

    # 2. Simulate Candidate Diligence completion (audited true numbers)
    audited_dossier = {
        "status": "ok",
        "ticker": "GOOG",
        "candidate_id": "cand_goog",
        "sec_financials": {
            "status": "ok",
            "ticker": "GOOG",
            "periods": ["Q4 2025"],
            "revenue": {"Q4 2025": 113829000000.0},
            "gross_margin_pct": {"Q4 2025": 0.598},
            "cash_from_operations": {"Q4 2025": 52402000000.0},  # Audited Q4 CFO
            "capex": {"Q4 2025": 27851000000.0},
            "ttm_fcf": 53273000000.0,  # Audited True TTM FCF
        },
        "valuation": {
            "fair_value": 380.0,
            "bear_floor": 290.0,
        },
        "market_context": {
            "quote": {"price": 340.0},
        },
    }

    diligence_tool_messages = [
        ToolMessage(
            tool_call_id="call_diligence",
            name="conduct_candidate_diligence",
            content=json.dumps(audited_dossier),
        )
    ]

    state = ingest_tool_results(state, diligence_tool_messages)

    # Verify candidate sec_financials was synchronized with the audited dossier
    assert state["candidates"]["cand_goog"]["sec_financials"]["cash_from_operations"]["Q4 2025"] == 52402000000.0
    assert state["candidates"]["cand_goog"]["sec_financials"]["ttm_fcf"] == 53273000000.0

    # 3. Verify build_source_registry extracts the audited numbers for CitationCard [1]
    cards = build_source_registry(state)
    assert len(cards) >= 1
    sec_card = next((c for c in cards if "SEC" in c.source_type or "XBRL" in c.title), None)
    assert sec_card is not None
    facts_str = " ".join(sec_card.facts)
    assert "CFO: $52.40B" in facts_str
    assert "TTM Free Cash Flow Base: $53.27B" in facts_str
    assert "$3.99B" not in facts_str
    assert "$-22.89B" not in facts_str


def test_asymmetry_downside_floor_prevents_ratio_inflation():
    """Verify minimum downside floor prevents divide-by-zero or micro-gap ratio inflation."""
    from app.agent.committee import run_investment_committee

    req = ResearchRequest(query="Analyze SYM", ticker="SYM", company="Symbotic")
    state = create_initial_state(req, case_id="case_sym")
    state["ticker"] = "SYM"
    state["market_context"] = {
        "quote": {"price": 100.0, "volume_20d_avg": 5_000_000, "volume": 6_000_000},
        "earnings_calendar": {"next_earnings_date": "2026-12-01"},
    }
    state["consensus_snapshot"] = {
        "price_targets": {"mean": {"value": 102.0}},  # +$2 upside
    }
    state["quant_report"] = {
        "valuation": {
            "fair_value_range": {"base": 102.0, "low": 99.99},  # Downside is only $0.01!
        }
    }
    state["adversarial_report"] = AdversarialReport(
        ticker="SYM",
        falsifiable_objections=("Margin decay",),
        numeric_kill_criteria=("margin < 10%",),
        bear_floor_price=99.99,
        bear_thesis_summary="Pricing erosion",
        status="available",
    )
    state["bull_report"] = BullReport(
        ticker="SYM",
        catalysts=("Tier 1 win",),
        operating_leverage_drivers=("Contract scale",),
        bull_target_price=102.0,
        bull_thesis_summary="Expanding backlog",
        invalidation_conditions=(),
        status="available",
    )
    state["evidence"] = [{"quote": "valid SEC quote", "accession": "0001", "source_url": "https://sec.gov"}]

    class FakeCommitteeModel:
        def invoke(self, messages):
            class Resp:
                content = '{"verdict": "APPROVED", "target_price": 102.0, "thesis_summary": "ok", "macro_headwinds": [], "key_risks": [], "catalysts": []}'
            return Resp()

    res = run_investment_committee(state, model=FakeCommitteeModel())
    verdict = res.get("ic_verdict")
    assert verdict is not None
    # Without floor, ratio would be 2.00 / 0.01 = 200.0x!
    # With floor, downside = max(0.01, 100 * 0.03, 1.0) = 3.00, ratio = 2.00 / 3.00 = 0.67x -> REJECTED
    assert verdict.verdict != "APPROVED"
    assert "FAIL" in verdict.passing_discipline_checks["asymmetry_gate"]

