"""Tests for the SEC Specialist Analyst sub-agent capability."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage

from app.agent.tools import create_agent_tools
from app.agent.tool_result_ingestion import ingest_tool_results
from app.sec.agent import run_sec_investigation, SEC_ANALYST_SYSTEM_PROMPT
from app.sec.schemas import FilingMetadata


class MockSecAnalystModel:
    """Deterministic LLM test double for SEC analyst synthesis."""

    def invoke(self, messages: list[Any]) -> AIMessage:
        return AIMessage(
            content=json.dumps({
                "assessment": "CONFIRMED",
                "synthesis": "Microsoft reported $35.8B in capital expenditures primarily supporting datacenter AI infrastructure.",
                "findings": [
                    "Datacenter purchase commitments scaled past $18B.",
                    "No material internal control weaknesses disclosed.",
                ],
            })
        )


def test_investigate_sec_tool_registration():
    """Verify investigate_sec is present in the default tool registry."""
    tools = {t.name: t for t in create_agent_tools()}
    assert "investigate_sec" in tools
    assert "verify_sec_claim" in tools
    assert "get_sec_financials" in tools


def test_investigate_sec_execution_with_mock_model(tmp_path: Path, monkeypatch):
    """Verify run_sec_investigation retrieves chunks and formats cited synthesis."""
    from app.sec.retrieval import RetrievalResult, RetrievedSecChunk
    from app.sec.corpus import CorpusChunk

    sample_text = "Capital expenditures for property and equipment were $35.8 billion, primarily for datacenters and network equipment supporting cloud and artificial intelligence infrastructure."
    fake_chunk = CorpusChunk(
        chunk_id="chunk-msft-001",
        ordinal=0,
        accession="0000789019-26-000001",
        form="10-K",
        filing_date=date.fromisoformat("2026-02-01"),
        document_name="primary_doc.htm",
        source_url="https://www.sec.gov/Archives/edgar/data/789019/form10k.htm",
        relative_path=Path("sec/documents/primary_doc.htm"),
        start_offset=0,
        end_offset=len(sample_text),
        text=sample_text,
    )
    fake_retrieved = RetrievedSecChunk(
        chunk=fake_chunk,
        dense_rank=1,
        sparse_rank=1,
        rrf_score=0.88,
        rerank_score=0.88,
        rerank_status="NOT_APPLIED",
    )

    # Mock search_sec_corpus to return our fake chunk
    monkeypatch.setattr(
        "app.sec.agent.search_sec_corpus",
        lambda *args, **kwargs: RetrievalResult(results=(fake_retrieved,), error=None),
    )
    # Ensure index exists check passes
    target_dir = tmp_path / "case_test" / "candidates" / "cand_msft" / "sec" / "index"
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "sec.faiss").write_bytes(b"mock_index")

    result = run_sec_investigation(
        cases_root=tmp_path,
        case_id="case_test",
        ticker="MSFT",
        task="What are Microsoft's datacenter capex commitments?",
        form="10-K",
        candidate_id="cand_msft",
        model=MockSecAnalystModel(),
    )

    assert result["status"] == "ok"
    assert result["ticker"] == "MSFT"
    assert result["candidate_id"] == "cand_msft"
    assert result["assessment"] == "CONFIRMED"
    assert "35.8B" in result["synthesis"]
    assert len(result["evidence"]) == 1
    assert result["evidence"][0]["form"] == "10-K"
    assert result["evidence"][0]["accession"] == "0000789019-26-000001"
    assert "Capital expenditures" in result["evidence"][0]["quote"]


def test_investigate_sec_tool_invocation_and_ingestion(tmp_path: Path, monkeypatch):
    """Verify investigate_sec tool call is ingested into candidate evidence."""
    tools = {t.name: t for t in create_agent_tools(cases_root=tmp_path, case_id="case_sec_e2e")}
    inv_tool = tools["investigate_sec"]

    fake_res = {
        "status": "ok",
        "ticker": "MSFT",
        "candidate_id": "cand_msft",
        "task": "Check active shelf offerings",
        "assessment": "INVESTIGATION_COMPLETE",
        "synthesis": "No active S-3 shelf offerings or ATM programs disclosed.",
        "findings": ["Clean balance sheet capital structure."],
        "evidence": [
            {
                "quote": "As of December 31, 2025, the company had no active At-The-Market offering facilities.",
                "form": "10-Q",
                "filing_date": "2026-01-28",
                "accession": "0000789019-26-000010",
                "source_url": "https://www.sec.gov/filing10q",
            }
        ],
    }
    monkeypatch.setattr(
        "app.sec.agent.run_sec_investigation",
        lambda *args, **kwargs: fake_res,
    )

    raw_output = inv_tool.invoke({
        "ticker": "MSFT",
        "task": "Check active shelf offerings",
        "candidate_id": "cand_msft",
    })
    payload = json.loads(raw_output)
    assert payload["status"] == "ok"
    assert len(payload["evidence"]) == 1

    # Ingest tool message
    tool_msg = ToolMessage(
        content=raw_output,
        name="investigate_sec",
        tool_call_id="call-sec-inv-1",
    )
    state = {
        "candidates": {
            "cand_msft": {"candidate_id": "cand_msft", "ticker": "MSFT", "evidence": []}
        },
        "research_intent": {"requires_candidate_workspaces": True},
        "evidence": [],
    }
    updates = ingest_tool_results(state, [tool_msg])

    cand = updates["candidates"]["cand_msft"]
    assert len(cand["evidence"]) == 1
    assert cand["evidence"][0]["form"] == "10-Q"
    assert "At-The-Market" in cand["evidence"][0]["quote"]
    assert cand["evidence"][0]["accession"] == "0000789019-26-000010"


def test_verify_sec_claim_resolves_with_ticker(tmp_path: Path, monkeypatch):
    """Verify verify_sec_claim accepts bare ticker without requiring manual corpus_id."""
    tools = {t.name: t for t in create_agent_tools(cases_root=tmp_path, case_id="case_verify")}
    verify_tool = tools["verify_sec_claim"]

    from app.sec.schemas import SECVerification, SecEvidence
    from app.sec.verifier import VerificationResult

    fake_verif = SECVerification(
        claim="Microsoft entered into a binding deal",
        verdict="CONTRADICTED",
        confidence=0.95,
        explanation="Agreement is non-binding LOI.",
        evidence_for=(),
        evidence_against=(
            SecEvidence(
                accession="0000789019-26-000099",
                form="8-K",
                filing_date=date.fromisoformat("2026-03-01"),
                document="primary_doc.htm",
                quote="The LOI is preliminary and non-binding.",
                source_url="https://www.sec.gov/8k",
            ),
        ),
        material_sec_facts={},
        missing_evidence=(),
        suggested_document_types=(),
    )

    monkeypatch.setattr(
        "app.agent.tools._verify_sec_claim",
        lambda *args, **kwargs: VerificationResult(verification=fake_verif, error=None),
    )

    # Ensure index exists
    cand_dir = tmp_path / "case_verify" / "candidates" / "cand_msft" / "sec" / "index"
    cand_dir.mkdir(parents=True, exist_ok=True)
    (cand_dir / "sec.faiss").write_bytes(b"mock_index")

    raw_output = verify_tool.invoke({
        "claim": "Microsoft entered into a binding deal",
        "ticker": "MSFT",
        "candidate_id": "cand_msft",
    })
    payload = json.loads(raw_output)
    assert payload["status"] == "ok"
    assert payload["verification"]["verdict"] == "CONTRADICTED"
    assert "non-binding" in payload["verification"]["evidence_against"][0]["quote"]
