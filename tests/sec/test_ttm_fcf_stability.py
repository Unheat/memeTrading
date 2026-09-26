"""Follow-up stability tests: TTM FCF determinism and unified reverse-DCF FCF base.

Root cause discovered in the post-fix e2e run: the provider ttm_fcf silently flipped
between fetches (partial XBRL windows fell back to annualization), giving the
expectations prelim a different FCF base than the quant DCF — the true source of the
"two reverse DCFs disagree" audit finding.
"""
import json

import pytest

from app.sec.financials import _compute_ttm_fcf


def test_ttm_fcf_full_window_sums_four_quarters():
    fcf = {"Q2 2026": -5.85e9, "Q1 2026": 10.12e9, "Q4 2025": -23.86e9, "Q3 2025": 30.7e9}
    periods = ["Q2 2026", "Q1 2026", "Q4 2025", "Q3 2025"]
    assert _compute_ttm_fcf(fcf, periods) == pytest.approx(sum(fcf.values()), rel=1e-6)


def test_ttm_fcf_partial_window_is_none():
    fcf = {"Q2 2026": -5.85e9, "Q1 2026": 10.12e9, "Q4 2025": None, "Q3 2025": 30.7e9}
    assert _compute_ttm_fcf(fcf, list(fcf.keys())) is None


def test_ttm_fcf_single_quarter_is_not_annualized():
    # The old fallback annualized one quarter (fcf[0] * 4) — removed for stability.
    fcf = {"Q2 2026": 13.3e9}
    assert _compute_ttm_fcf(fcf, ["Q2 2026"]) is None


def test_expectations_prelim_uses_quant_fcf_base_even_with_positive_ttm():
    """The prelim must not trust a positive provider ttm_fcf; capex-spike normalization
    (same as run_quant_analysis) governs, so both reverse DCFs share one FCF base."""
    from app.agent.expectations import run_expectations_analyst
    from app.agent.state import ResearchRequest, create_initial_state

    req = ResearchRequest(query="Analyze GOOG", ticker="GOOG", company="Alphabet")
    state = create_initial_state(req, case_id="case_ttm_stability")
    state["market_context"] = {
        "quote": {"price": 341.0799865722656},
        "fundamentals": {"shares_outstanding": {"value": 5_527_000_000.0, "reliable": True}},
    }
    state["sec_financials"] = {
        "status": "ok",
        "periods": ["Q2 2026"],
        "cash_from_operations": {"Q2 2026": 39_069_000_000.0},
        "capex": {"Q2 2026": 44_924_000_000.0},
        "revenue": {"Q2 2026": 119_796_000_000.0},
        "cash_and_equivalents": {"Q2 2026": 242_470_000_000.0},
        "total_debt": {"Q2 2026": 100_160_000_000.0},
        "ttm_fcf": 53_273_000_000.0,  # positive provider value — previously trusted blindly
    }

    class _Garbage:
        """Model that fails to parse, forcing the deterministic fallback path."""

        def invoke(self, messages):
            return type("R", (), {"content": "not json"})()

    result = run_expectations_analyst(state, model=_Garbage())
    gap = result["expectation_gap"]
    # fcf base = (39.069B - min(44.924B, 15% x 119.796B)) * 4 = 84.3984B -> implied 8.86%
    assert gap["implied_fcf_growth_rate"] == pytest.approx(0.0886, abs=5e-4)
    assert gap["status"] == "degraded"  # model failed; deterministic fields still honest
