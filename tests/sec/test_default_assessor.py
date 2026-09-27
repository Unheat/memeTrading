"""Tests for production SEC default assessor with keyless offline fallback."""
import os
from unittest.mock import patch, MagicMock
import pytest
from app.config import AppConfig, LLMConfig, ModelEndpointConfig
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


def _keyless_config() -> AppConfig:
    """Return configuration whose primary endpoint has no credential source."""
    return AppConfig(
        llm=LLMConfig(models=[ModelEndpointConfig(model="openai/gpt-4o-mini")])
    )


def test_default_assessor_offline_fallback_fails_closed_without_language_inference():
    """Return no inferred support or contradiction when structured assessment is unavailable."""
    with patch.dict("os.environ", {}, clear=True), patch(
        "app.config.load_config", return_value=_keyless_config()
    ):
        assessor = get_default_sec_assessor()
        assert callable(assessor)

        chunks = [
            _make_retrieved_chunk("c1", "The agreement is a non-binding letter of intent."),
            _make_retrieved_chunk("c2", "Gross margin expanded to 36 percent."),
        ]
        result = assessor("Company signed a binding definitive agreement", chunks)

    assert result["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert result["evidence_for_chunk_ids"] == []
    assert result["evidence_against_chunk_ids"] == []


def test_default_assessor_insufficient_evidence():
    """Return insufficient evidence when no structured assessment can be made."""
    with patch.dict("os.environ", {}, clear=True), patch(
        "app.config.load_config", return_value=_keyless_config()
    ):
        assessor = get_default_sec_assessor()
        res = assessor("Unrelated aerospace satellite launch", [])
        assert res["verdict"] == "INSUFFICIENT_EVIDENCE"
        assert len(res["missing_evidence"]) > 0


def test_default_assessor_normalizes_openai_gateway_model_and_fails_closed(monkeypatch):
    """Use gateway-native model IDs and degrade safely on a provider outage."""
    from app.config import AppConfig, LLMConfig, ModelEndpointConfig
    from app.sec.verifier import AssessorUnavailableError

    captured: dict[str, object] = {}

    def unavailable_assessor(_config):
        """Capture configuration and simulate a temporary provider failure."""
        captured["model"] = _config.model

        def assess(_: str, __):
            """Raise the provider error supplied by the test."""
            raise AssessorUnavailableError()

        return assess

    config = AppConfig(
        llm=LLMConfig(models=[ModelEndpointConfig(model="openai/fastg", api_key_env="TEST_ASSESSOR_KEY", base_url="http://localhost:20128/v1")])
    )
    monkeypatch.setenv("TEST_ASSESSOR_KEY", "test-key")
    monkeypatch.setattr("app.config.load_config", lambda: config)
    monkeypatch.setattr(
        "app.sec.openai_compatible_assessor.create_openai_compatible_sec_assessor",
        unavailable_assessor,
    )

    assessor = get_default_sec_assessor()
    result = assessor("Revenue increased", [_make_retrieved_chunk("c1", "Revenue increased")])

    assert captured["model"] == "fastg"
    assert result["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert result["evidence_for_chunk_ids"] == []
