"""Tests for memo rendering and serialization."""
import json
import pytest
from app.agent.memo import render_forensic_memo, serialize_investigation_json
from app.agent.state import ResearchRequest, create_initial_state


def test_render_forensic_memo_includes_required_sections():
    req = ResearchRequest(query="Check XYZ buyout rumors", ticker="XYZ", company="XYZ Tech Inc")
    state = create_initial_state(req, case_id="case_123")
    state["trigger"] = {"query": "Buyout rumor on WSB", "theme": "merger"}
    state["root_claims"] = ["Signed definitive agreement with BigCorp for $10/share"]
    state["evidence"] = [
        {
            "form": "8-K",
            "accession": "0001193125-26-123456",
            "filing_date": "2026-09-01",
            "source_url": "https://www.sec.gov/Archives/edgar/data/123/000119312526123456/doc.htm",
            "quote": "The letter of intent is non-binding and subject to due diligence.",
        }
    ]
    state["contradictions"] = [
        {"claim": "Definitive agreement", "finding": "LOI is non-binding per 8-K"}
    ]
    state["unresolved_questions"] = ["Will financing materialize?"]
    state["market_context"] = {
        "returns": {"1m": {"value": 0.45}},
        "volume_ratio_20d": {"value": 3.2},
    }

    final_text = "The buyout hype is speculative and contradicted by official 8-K filings."
    memo_md = render_forensic_memo(state, final_text)

    # Investor-note opening (from financial-research-workshop format)
    assert "**Headline**:" in memo_md
    assert "**Bottom Line**:" in memo_md
    assert "The buyout hype is speculative" in memo_md  # bottom line = first sentence(s)
    assert "**Drivers**:" in memo_md
    assert "**Risks / What we're watching**:" in memo_md

    # Check key headings and content
    assert "# Meme Market Forensic Memo: $XYZ" in memo_md
    assert "XYZ Tech Inc" in memo_md
    assert "## 1. Narrative Origin & Social Trigger" in memo_md
    assert "## 2. Core Claims & Reality Check" in memo_md
    assert "## 3. SEC Filing Evidence & Audit Trail" in memo_md
    assert "0001193125-26-123456" in memo_md  # SEC receipt cited
    assert "non-binding and subject to due diligence" in memo_md
    assert "## 6. Market Context & Pricing Check" in memo_md
    assert "## Wall Street Expectations vs Ground Reality" in memo_md
    assert "No institutional analyst coverage" in memo_md  # no consensus data yet
    assert "## 7. Remaining Uncertainties" in memo_md
    assert "## 8. Forensic Conclusion" in memo_md
    assert final_text in memo_md


def test_render_forensic_memo_with_consensus_and_gap():
    req = ResearchRequest(query="Check MU memory demand", ticker="MU", company="Micron")
    state = create_initial_state(req, case_id="case_mu")
    state["consensus_snapshot"] = {
        "price_targets": {"low": {"value": 90.0}, "mean": {"value": 130.0}, "high": {"value": 180.0}},
        "eps_estimates": [
            {"metric": "eps", "period": "0y", "avg": 3.2, "low": 2.9, "high": 3.55,
             "growth": 0.21, "n_analysts": 44},
        ],
        "revenue_estimates": [
            {"metric": "revenue", "period": "0y", "avg": 42.1e9, "low": 40.0e9, "high": 44.5e9,
             "growth": 0.18, "n_analysts": 38},
        ],
    }
    state["expectation_gap"] = {
        "verdict": "Consensus underprices verified demand signal",
        "rationale": "Ground reality shows inventory drawdown while consensus models 21% EPS growth.",
    }

    memo_md = render_forensic_memo(state, "Synthesis text.")

    assert "## Wall Street Expectations vs Ground Reality" in memo_md
    assert "| EPS | 0y | 3.2 |" in memo_md
    assert "| REVENUE | 0y |" in memo_md
    assert "low 90.0 | mean 130.0 | high 180.0" in memo_md
    assert "**Expectation-gap verdict**: Consensus underprices verified demand signal" in memo_md
    assert "inventory drawdown" in memo_md


def test_serialize_investigation_json():
    req = ResearchRequest(query="Check ABC", ticker="ABC")
    state = create_initial_state(req, case_id="case_abc")
    data = serialize_investigation_json(state, memo_md="# Memo")

    assert data["case_id"] == "case_abc"
    assert data["ticker"] == "ABC"
    assert data["memo_markdown"] == "# Memo"
    assert isinstance(data["evidence"], list)
