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


def test_run_candidate_diligence_staged_concurrency_execution(monkeypatch):
    """Verify Stage 1 (Exp/For/Moat) and Stage 3 (Bull/Bear) run concurrently with Stage 2 receiving assumptions."""
    call_order = []

    def mock_exp(cand_state, model):
        call_order.append("exp")
        return {"expectation_gap": {"assumptions": {"revenue_growth_rate": 0.15}}}

    def mock_for(cand_state, model):
        call_order.append("forensic")
        return {"forensic_report": {"verdict": "CLEAN"}}

    def mock_moat(cand_state, model):
        call_order.append("moat")
        return {"moat_report": {"analysis": {"moat_rating": "WIDE"}}}

    def mock_quant(cand_state):
        # Assert that expectation_gap from Stage 1 is present in cand_state
        assert cand_state.get("expectation_gap") == {"assumptions": {"revenue_growth_rate": 0.15}}
        call_order.append("quant")
        return {"quant_report": {"valuation": {"fair_value": 500.0, "implied_fcf_growth_rate": 0.08}}}

    def mock_bull(cand_state, model):
        call_order.append("bull")
        class FakeBull:
            catalysts = ("Catalyst A", "Catalyst B")
            bull_thesis_summary = "Bull thesis"
        return {"bull_report": FakeBull()}

    def mock_bear(cand_state, model):
        call_order.append("bear")
        class FakeBear:
            numeric_kill_criteria = ("Kill 1",)
            bear_thesis_summary = "Bear thesis"
            bear_floor_price = 300.0
        return {"adversarial_report": FakeBear()}

    monkeypatch.setattr("app.agent.diligence.run_expectations_analyst", mock_exp)
    monkeypatch.setattr("app.agent.diligence.run_forensic_analysis", mock_for)
    monkeypatch.setattr("app.agent.diligence.run_moat_analysis", mock_moat)
    monkeypatch.setattr("app.agent.diligence.run_quant_analysis", mock_quant)
    monkeypatch.setattr("app.agent.diligence.run_bull_advocate", mock_bull)
    monkeypatch.setattr("app.agent.diligence.run_adversarial_red_team", mock_bear)

    workspace = {
        "ticker": "MSFT",
        "market_context": {"quote": {"price": 450.0}},
        "sec_financials": {"status": "ok", "periods": ["2026-Q2"], "cash_from_operations": {"2026-Q2": 35e9}, "capex": {"2026-Q2": 15e9}},
    }

    dossier = run_candidate_diligence("MSFT", candidate_id="cand_msft", candidate_workspace=workspace, model=object())
    assert dossier["status"] == "ok"
    assert dossier["forensic_verdict"] == "CLEAN"
    assert dossier["moat_rating"] == "WIDE"
    assert dossier["valuation"]["fair_value"] == 500.0
    assert dossier["bull_catalysts"] == ["Catalyst A", "Catalyst B"]
    assert dossier["bear_kill_triggers"] == ["Kill 1"]

    # Verify staged execution order: Stage 1 set -> Stage 2 -> Stage 3 set
    assert set(call_order[:3]) == {"exp", "forensic", "moat"}
    assert call_order[3] == "quant"
    assert set(call_order[4:]) == {"bull", "bear"}


def test_run_candidate_diligence_shields_individual_specialist_exceptions(monkeypatch):
    """Verify an exception in one specialist does not crash the entire candidate diligence."""
    def fail_moat(cand_state, model):
        raise RuntimeError("Moat LLM rate limit")

    monkeypatch.setattr("app.agent.diligence.run_moat_analysis", fail_moat)

    workspace = {
        "ticker": "NVDA",
        "market_context": {"quote": {"price": 120.0}},
        "sec_financials": {"status": "ok", "periods": ["2026-Q2"], "cash_from_operations": {"2026-Q2": 10e9}, "capex": {"2026-Q2": 2e9}},
    }
    dossier = run_candidate_diligence("NVDA", candidate_workspace=workspace, model=object())
    assert dossier["status"] == "ok"
    assert dossier["ticker"] == "NVDA"
    assert dossier["moat_rating"] is None

