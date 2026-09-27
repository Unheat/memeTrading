"""Unit tests for closed-world grounded synthesis, schemas, and evidence-ID validation."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agent.grounded_synthesis import (
    GroundedClaim,
    GroundedSynthesis,
    build_evidence_packet,
    materialize_evidence_records,
    validate_grounded_synthesis,
)
from app.agent.state import ResearchRequest, create_initial_state


def test_grounded_synthesis_schema_strictness():
    """GroundedClaim and GroundedSynthesis forbid extra fields and enforce types."""
    # Valid claim
    claim = GroundedClaim(
        claim_id="claim_1",
        statement="Micron reported $34.8B in quarterly revenue.",
        claim_type="financial_metric",
        evidence_link_ids=["fact_mu_rev_2026q3"],
        is_inference=False,
    )
    assert claim.claim_id == "claim_1"

    # Extra fields are strictly forbidden
    with pytest.raises(ValidationError):
        GroundedClaim(
            claim_id="claim_2",
            statement="Statement",
            claim_type="financial_metric",
            hallucinated_field="forbidden",  # type: ignore[call-arg]
        )


def test_build_evidence_packet_scoping():
    """build_evidence_packet scopes facts to candidate when candidate_id is specified."""
    req = ResearchRequest(query="Compare NVDA and GOOGL", ticker=None, requested_ranking_count=2)
    state = create_initial_state(req, case_id="case_packet")
    state["candidates"] = {
        "cand_nvda": {
            "candidate_id": "cand_nvda",
            "ticker": "NVDA",
            "fact_cards": [
                {"fact_id": "fact_nvda_rev", "metric_key": "revenue", "value": 35000000000.0, "candidate_id": "cand_nvda"},
            ],
            "evidence": [
                {"excerpt_id": "exc_nvda_h100", "quote": "Demand for Hopper remains strong.", "candidate_id": "cand_nvda"},
            ],
        },
        "cand_googl": {
            "candidate_id": "cand_googl",
            "ticker": "GOOGL",
            "fact_cards": [
                {"fact_id": "fact_googl_rev", "metric_key": "revenue", "value": 95000000000.0, "candidate_id": "cand_googl"},
            ],
            "evidence": [
                {"excerpt_id": "exc_googl_tpu", "quote": "TPU deployments accelerated in Q2.", "candidate_id": "cand_googl"},
            ],
        },
    }

    # NVDA scoped packet must not include GOOGL items
    nvda_packet = build_evidence_packet(state, candidate_id="cand_nvda")
    assert "fact_nvda_rev" in nvda_packet["items"]
    assert "exc_nvda_h100" in nvda_packet["items"]
    assert "fact_googl_rev" not in nvda_packet["items"]
    assert "exc_googl_tpu" not in nvda_packet["items"]

    # Global packet contains both
    all_packet = build_evidence_packet(state)
    assert "fact_nvda_rev" in all_packet["items"]
    assert "fact_googl_rev" in all_packet["items"]


def test_validate_grounded_synthesis_valid_references():
    """Claims citing existing evidence IDs pass validation and generate ledger records."""
    packet = {
        "items": {
            "fact_1": {"item_id": "fact_1", "candidate_id": "cand_mu", "fact_summary": "Gross margin 36.2%"},
            "exc_1": {"item_id": "exc_1", "candidate_id": "cand_mu", "fact_summary": "Primary 10-Q excerpt"},
        }
    }
    synthesis = GroundedSynthesis(
        executive_claims=[
            GroundedClaim(
                claim_id="exec_1",
                statement="Gross margin expanded to 36.2% per SEC filings.",
                claim_type="financial_metric",
                evidence_link_ids=["fact_1", "exc_1"],
                is_inference=False,
            )
        ],
        findings=[
            GroundedClaim(
                claim_id="find_1",
                statement="Margin trajectory suggests operating leverage.",
                claim_type="expectation_gap",
                evidence_link_ids=[],
                is_inference=True,
            )
        ],
    )

    result = validate_grounded_synthesis(synthesis, packet, allowed_candidate_id="cand_mu")
    assert result["passed"] is True
    assert result["errors"] == []
    assert len(result["claim_records"]) == 2
    assert len(result["evidence_links"]) == 2
    assert result["claim_records"][0]["status"] == "supported"


def test_validate_grounded_synthesis_unknown_id_fails():
    """Citing an evidence ID not present in the packet fails validation."""
    packet = {
        "items": {
            "fact_1": {"item_id": "fact_1", "candidate_id": "cand_mu", "fact_summary": "Gross margin 36.2%"},
        }
    }
    synthesis = GroundedSynthesis(
        executive_claims=[
            GroundedClaim(
                claim_id="exec_1",
                statement="Micron secured $10B in secret financing.",
                claim_type="financial_metric",
                evidence_link_ids=["hallucinated_fact_999"],
                is_inference=False,
            )
        ]
    )

    result = validate_grounded_synthesis(synthesis, packet, allowed_candidate_id="cand_mu")
    assert result["passed"] is False
    assert any("hallucinated_fact_999" in err for err in result["errors"])


def test_validate_grounded_synthesis_cross_candidate_fails():
    """Citing another candidate's evidence ID fails cross-candidate validation."""
    packet = {
        "items": {
            "fact_nvda": {"item_id": "fact_nvda", "candidate_id": "cand_nvda", "fact_summary": "NVDA margin 75%"},
        }
    }
    synthesis = GroundedSynthesis(
        executive_claims=[
            GroundedClaim(
                claim_id="exec_1",
                statement="Google margin reached 75%.",
                claim_type="financial_metric",
                evidence_link_ids=["fact_nvda"],
                is_inference=False,
            )
        ]
    )

    result = validate_grounded_synthesis(synthesis, packet, allowed_candidate_id="cand_googl")
    assert result["passed"] is False
    assert any("cross-cites candidate" in err for err in result["errors"])


def test_validate_grounded_synthesis_unsupported_factual_claim_fails():
    """Asserting a factual claim with no evidence links fails validation."""
    packet = {"items": {}}
    synthesis = GroundedSynthesis(
        executive_claims=[
            GroundedClaim(
                claim_id="exec_1",
                statement="Revenue grew 50%.",
                claim_type="financial_metric",
                evidence_link_ids=[],  # missing required evidence links for factual claim
                is_inference=False,
            )
        ]
    )

    result = validate_grounded_synthesis(synthesis, packet)
    assert result["passed"] is False
    assert any("lacks supporting evidence links" in err for err in result["errors"])


def test_materialize_evidence_records():
    """materialize_evidence_records assigns excerpt_id and populates source_records."""
    state = {
        "evidence": [
            {
                "quote": "Revenue reached record highs in Q3.",
                "source_url": "https://www.sec.gov/Archives/edgar/data/123/doc.htm",
                "form": "10-Q",
            }
        ],
        "source_records": [],
    }
    materialize_evidence_records(state)
    assert state["evidence"][0]["excerpt_id"].startswith("exc_")
    assert state["evidence"][0]["source_id"].startswith("src_")
    assert len(state["source_records"]) == 1
    assert state["source_records"][0]["status"] == "read"
    assert state["source_records"][0]["url"] == "https://www.sec.gov/Archives/edgar/data/123/doc.htm"
