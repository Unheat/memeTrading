"""Batch C acceptance tests: completeness and hygiene (audit 2026-09-26).

Covers Fix 5 (moat report travels through dossier), Fix 9 (issuer-PDF gap filter),
and hardening (ToolCallGuard hashable coercion, Kelly JS/Python parity).
"""
import json
import math
import subprocess
from pathlib import Path

import pytest

from app.agent.diligence import build_diligence_dossier
from app.agent.graph import _is_issuer_pdf
from app.agent.tools import ToolCallGuard


# --- Fix 5: moat report travels in the dossier ----------------------------------------

class _FakeBull:
    """Minimal bull report stand-in."""

    catalysts = ["Catalyst 1"]
    bull_thesis_summary = "Upside."
    bull_target_price = 500.0
    status = "available"


class _FakeBear:
    """Minimal bear report stand-in."""

    numeric_kill_criteria = ["Kill 1"]
    bear_thesis_summary = "Downside."
    bear_floor_price = 195.0
    status = "available"


def test_dossier_carries_moat_report_and_bull_target():
    cand_state = {
        "company": "Alphabet",
        "forensic_report": {"verdict": "CLEAN_INVESTMENT_GRADE"},
        "moat_report": {"status": "available", "analysis": {"moat_rating": "WIDE", "durability_score": 9}},
        "market_context": {"quote": {"price": 341.0}},
        "sec_financials": {"status": "ok"},
        "expectation_gap": {"verdict": "ALREADY_PRICED_IN"},
        "quant_report": {"valuation": {"fair_value_range": {"low": 178.0, "base": 254.0, "high": 408.0}}},
    }
    dossier = build_diligence_dossier(cand_state, _FakeBull(), _FakeBear(), "cand_goog", "GOOG")
    assert dossier["moat_report"]["analysis"]["moat_rating"] == "WIDE"
    assert dossier["moat_rating"] == "WIDE"
    assert dossier["bull_target_price"] == pytest.approx(500.0)
    assert dossier["bear_floor"] == pytest.approx(195.0)
    assert dossier["bull_report_status"] == "available"


def test_dossier_handles_missing_specialists():
    dossier = build_diligence_dossier({"company": "X", "quant_report": {}}, None, None, "cand_x", "X")
    assert dossier["moat_report"] is None
    assert dossier["bull_target_price"] is None
    assert dossier["status"] == "ok"


# --- Fix 9: issuer-PDF gap filter ------------------------------------------------------

def test_issuer_pdf_filter():
    sec_pdf = {"status": "discovered", "url": "https://www.sec.gov/Archives/edgar/x.pdf", "candidate_id": "cand_goog"}
    ir_pdf = {"status": "discovered", "url": "https://s206.q4cdn.com/479360582/earnings.pdf", "candidate_id": "cand_goog"}
    junk_pdf = {"status": "discovered", "url": "https://files.fasab.gov/pdffiles/handbook.pdf", "candidate_id": None}
    non_pdf = {"status": "discovered", "url": "https://example.com/article", "candidate_id": "cand_goog"}
    undiscovered = {"status": "read", "url": "https://www.sec.gov/y.pdf", "candidate_id": "cand_goog"}

    active = {"cand_goog"}
    assert _is_issuer_pdf(sec_pdf, active) is True
    assert _is_issuer_pdf(ir_pdf, active) is True  # bound to an active candidate
    assert _is_issuer_pdf(junk_pdf, active) is False  # unbound junk domain
    assert _is_issuer_pdf(non_pdf, active) is False
    assert _is_issuer_pdf(undiscovered, active) is False


# --- Hardening: ToolCallGuard hashable coercion ---------------------------------------

def test_guard_accepts_raw_dict_signature():
    guard = ToolCallGuard(max_identical=1)
    assert guard.check_and_record(("get_market_data", {"ticker": "GOOG", "limit": 5})) is False
    # Same logical args as dict and as sorted tuples must collide on the same key.
    assert guard.check_and_record(("get_market_data", (("limit", "5"), ("ticker", "GOOG")))) is True


def test_guard_thread_safety_with_mixed_signature_shapes():
    guard = ToolCallGuard(max_identical=2)
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=16) as ex:
        futs = [
            ex.submit(guard.check_and_record, ("t", {"ticker": "GOOG"} if i % 2 else (("ticker", "GOOG"),)))
            for i in range(32)
        ]
        results = [f.result() for f in futs]
    admitted = sum(1 for r in results if r is False)
    assert admitted == 2  # both shapes map to the same logical call


# --- Hardening: Kelly JS/Python parity -------------------------------------------------

def test_kelly_js_python_parity():
    """The JS calculator and Python committee Kelly implementations must agree on f*."""
    from app.market.metrics import compute_fractional_kelly

    upside_pct, downside_pct, win_prob = 20.0, 10.0, 0.60
    python_fractional = compute_fractional_kelly(
        upside_pct=upside_pct,
        downside_pct=downside_pct,
        win_prob=win_prob,
        fraction=1.0,  # full Kelly for parity
        max_position_cap=1.0,
        max_loss_budget=10.0,  # unbind constraints for the raw f* comparison
    )
    # Python: (p*b - q)/b == p - q/b
    expected = (win_prob * (upside_pct / downside_pct) - (1 - win_prob)) / (upside_pct / downside_pct)
    assert math.isclose(python_fractional, expected, rel_tol=1e-9)

    calculator_uri = (Path(__file__).resolve().parents[2] / "app" / "valuation" / "calculator.mjs").as_uri()
    script = (
        f"import {{ computeKellySizing }} from '{calculator_uri}';"
        "const k = computeKellySizing({upsidePct: 20.0, downsidePct: 10.0, probWin: 0.6,"
        " maxDrawdownBudget: 1000, maxPositionCap: 1.0, fraction: 'full'});"
        "console.log(JSON.stringify({full: k.full_kelly_pct}));"
    )
    node = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        capture_output=True, text=True, timeout=30,
    )
    assert node.returncode == 0, node.stderr
    full_pct = float(json.loads(node.stdout.strip())["full"].rstrip("%"))
    assert math.isclose(full_pct / 100.0, expected, rel_tol=1e-6)
