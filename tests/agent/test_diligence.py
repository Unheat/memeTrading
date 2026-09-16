"""Tests for isolated candidate diligence sub-agent execution."""
import json
from unittest.mock import patch
from app.agent.diligence import run_candidate_diligence
from app.agent.tools import create_agent_tools


def test_run_candidate_diligence_produces_structured_dossier():
    """Verify run_candidate_diligence executes specialist analysis and returns structured dossier."""
    workspace = {
        "ticker": "MSFT",
        "company": "Microsoft Corporation",
        "market_context": {
            "quote": {"price": 450.0},
            "fundamentals": {"shares_outstanding": 7.4e9},
            "currency": "USD",
        },
        "sec_financials": {
            "status": "ok",
            "periods": ["2026-Q2"],
            "cash_from_operations": {"2026-Q2": 35e9},
            "capex": {"2026-Q2": 15e9},
            "cash_and_equivalents": {"2026-Q2": 80e9},
            "total_debt": {"2026-Q2": 45e9},
            "gross_margin_pct": {"2026-Q2": 0.70},
        },
    }

    dossier = run_candidate_diligence("MSFT", candidate_id="cand_msft", candidate_workspace=workspace)
    assert dossier["status"] == "ok"
    assert dossier["ticker"] == "MSFT"
    assert dossier["candidate_id"] == "cand_msft"
    assert "valuation" in dossier
    assert "bull_catalysts" in dossier
    assert "bear_kill_triggers" in dossier


def test_conduct_candidate_diligence_tool_registration(tmp_path):
    """Verify conduct_candidate_diligence is available in agent tools."""
    tools = create_agent_tools(cases_root=tmp_path)
    tool_names = [t.name for t in tools]
    assert "conduct_candidate_diligence" in tool_names
