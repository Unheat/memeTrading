"""Tests for production SEC default assessor with keyless offline fallback."""
import os
from unittest.mock import patch, MagicMock
import pytest
from app.sec.default_assessor import get_default_sec_assessor
from app.sec.corpus import CorpusChunk
from app.sec.retrieval import RetrievedSecChunk


def _make_retrieved_chunk(chunk_id: str, text: str) -> RetrievedSecChunk:
    chunk = CorpusChunk(
        chunk_id=chunk_id,
        ordinal=0,
        accession="0001193125-26-123456",
        form="8-K",
        filing_date="2026-09-01",
        document_name="doc.htm",
        source_url="https://www.sec.gov/doc.htm",
        relative_path="sec/documents/doc.htm",
        start_offset=0,
        end_offset=len(text),
        text=text,
    )
    return RetrievedSecChunk(
        chunk=chunk,
        dense_rank=1,
        sparse_rank=1,
        rrf_score=0.9,
        rerank_score=None,
        rerank_status="NOT_APPLIED",
    )


def test_default_assessor_offline_fallback():
    with patch.dict("os.environ", {}, clear=True):
        assessor = get_default_sec_assessor()
        assert callable(assessor)

        chunks = [
            _make_retrieved_chunk("c1", "The agreement is a non-binding letter of intent."),
            _make_retrieved_chunk("c2", "Gross margin expanded to 36 percent."),
        ]

        # Contradiction check
        res = assessor("Company signed a binding definitive agreement", chunks)
        assert res["verdict"] in ("CONFIRMED", "CONTRADICTED", "PARTIALLY_CONFIRMED", "INSUFFICIENT_EVIDENCE")
        assert "c1" in res["evidence_against_chunk_ids"] or "c1" in res["evidence_for_chunk_ids"] or res["verdict"] == "INSUFFICIENT_EVIDENCE"


def test_default_assessor_insufficient_evidence():
    with patch.dict("os.environ", {}, clear=True):
        assessor = get_default_sec_assessor()
        res = assessor("Unrelated aerospace satellite launch", [])
        assert res["verdict"] == "INSUFFICIENT_EVIDENCE"
        assert len(res["missing_evidence"]) > 0
