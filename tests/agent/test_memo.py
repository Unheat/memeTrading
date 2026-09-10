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

    # Check key headings and content
    assert "# Meme Market Forensic Memo: $XYZ" in memo_md
    assert "XYZ Tech Inc" in memo_md
    assert "## 1. Narrative Origin & Social Trigger" in memo_md
    assert "## 2. Core Claims & Reality Check" in memo_md
    assert "## 3. SEC Filing Evidence & Audit Trail" in memo_md
    assert "0001193125-26-123456" in memo_md  # SEC receipt cited
    assert "non-binding and subject to due diligence" in memo_md
    assert "## 6. Market Context & Pricing Check" in memo_md
    assert "## 7. Remaining Uncertainties" in memo_md
    assert "## 8. Forensic Conclusion" in memo_md
    assert final_text in memo_md


def test_serialize_investigation_json():
    req = ResearchRequest(query="Check ABC", ticker="ABC")
    state = create_initial_state(req, case_id="case_abc")
    data = serialize_investigation_json(state, memo_md="# Memo")

    assert data["case_id"] == "case_abc"
    assert data["ticker"] == "ABC"
    assert data["memo_markdown"] == "# Memo"
    assert isinstance(data["evidence"], list)
