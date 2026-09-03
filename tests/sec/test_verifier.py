"""Tests for constrained case-local SEC claim verification."""

from datetime import date
from pathlib import Path

from app.sec.corpus import prepare_sec_corpus
from app.sec.pull import SelectedSecDocument, pull_sec_filings
from app.sec.retrieval import build_sec_index
from app.sec.schemas import FilingMetadata


CASE_ID = "XYZ-2026-09-02-003"
PRIMARY_URL = "https://www.sec.gov/Archives/edgar/data/1/000000000026000004/report.txt"
EXHIBIT_URL = "https://www.sec.gov/Archives/edgar/data/1/000000000026000004/exhibit.txt"


def _embed(texts: list[str]) -> list[list[float]]:
    """Return deterministic local vectors for SEC verifier tests.

    Args:
        texts: Filing chunks or one retrieval query.

    Returns:
        Two-dimensional vectors derived only from local text.
    """
    return [[float("revenue" in text.lower()), float("debt" in text.lower())] for text in texts]


def _case(root: Path) -> Path:
    """Create one indexed two-document local SEC fixture.

    Args:
        root: Temporary root under which the case is stored.

    Returns:
        Indexed case directory.
    """
    filing = FilingMetadata(
        ticker="XYZ", cik="1", form="8-K", filing_date=date(2026, 9, 2),
        accession="0000000000-26-000004", filing_url=PRIMARY_URL,
        primary_document="report.txt", exhibits=("exhibit.txt",),
    )
    selections = (
        SelectedSecDocument(filing, "report.txt", PRIMARY_URL),
        SelectedSecDocument(filing, "exhibit.txt", EXHIBIT_URL),
    )
    pulled = pull_sec_filings(
        root,
        CASE_ID,
        selections,
        lambda url: {
            PRIMARY_URL: b"Revenue increased by 25 percent during the quarter.",
            EXHIBIT_URL: b"Debt remains outstanding under the credit agreement.",
        }[url],
    )
    assert pulled.error is None
    directory = root / CASE_ID
    assert prepare_sec_corpus(directory).error is None
    assert build_sec_index(directory, _embed).error is None
    return directory


def _assessment(verdict: str, chunks, *, evidence_for=(), evidence_against=(), missing=()):
    """Build a deterministic assessor mapping using retrieved chunk IDs.

    Args:
        verdict: Expected verification verdict.
        chunks: Retrieved local SEC candidate sequence.
        evidence_for: Candidate indexes supporting the claim.
        evidence_against: Candidate indexes contradicting the claim.
        missing: Missing evidence descriptions.

    Returns:
        Valid assessor response mapping.
    """
    return {
        "verdict": verdict,
        "confidence": 0.75,
        "explanation": "The local filing evidence was assessed against the supplied claim.",
        "evidence_for_chunk_ids": [chunks[index].chunk.chunk_id for index in evidence_for],
        "evidence_against_chunk_ids": [chunks[index].chunk.chunk_id for index in evidence_against],
        "material_sec_facts": {"reviewed_documents": len(chunks)},
        "missing_evidence": list(missing),
        "suggested_document_types": ["10-Q"],
    }


def test_verifier_returns_confirmed_explanation_and_immutable_receipt(tmp_path: Path) -> None:
    """Return a cited explanation while preserving chunk-owned SEC receipt fields.

    Args:
        tmp_path: Pytest-managed temporary filesystem root.

    Returns:
        None. Assertions verify grounded confirmation.
    """
    from app.sec.verifier import verify_sec_claim

    directory = _case(tmp_path / "cases")

    def assessor(claim: str, chunks):
        """Confirm using the retrieved revenue chunk.

        Args:
            claim: Supplied claim, checked for test coverage.
            chunks: Local retrieved candidate chunks.

        Returns:
            Structured local assessment.
        """
        assert "revenue" in claim.lower()
        revenue_index = next(index for index, item in enumerate(chunks) if "Revenue" in item.chunk.text)
        return _assessment("CONFIRMED", chunks, evidence_for=(revenue_index,))

    result = verify_sec_claim(directory, "Revenue increased by 25 percent.", lambda query: _embed([query])[0], assessor)

    assert result.error is None
    assert result.verification is not None
    assert result.verification.verdict == "CONFIRMED"
    assert result.verification.explanation
    evidence = result.verification.evidence_for[0]
    assert evidence.document == "report.txt"
    assert evidence.quote == "Revenue increased by 25 percent during the quarter."
    assert evidence.source_url == PRIMARY_URL


def test_verifier_handles_partial_contradicted_and_insufficient_verdicts(tmp_path: Path) -> None:
    """Preserve all remaining verdict categories and their required evidence.

    Args:
        tmp_path: Pytest-managed temporary filesystem root.

    Returns:
        None. Assertions verify schema-grounded verdict outputs.
    """
    from app.sec.verifier import verify_sec_claim

    directory = _case(tmp_path / "cases")
    claim = "Revenue is debt free."

    def partial(_: str, chunks):
        """Return support plus missing evidence for a partial response.

        Args:
            _: Ignored claim.
            chunks: Retrieved candidate chunks.

        Returns:
            Partial assessment mapping.
        """
        return _assessment("PARTIALLY_CONFIRMED", chunks, evidence_for=(0,), missing=("Debt maturity schedule",))

    def contradicted(_: str, chunks):
        """Return the debt chunk as counter-evidence.

        Args:
            _: Ignored claim.
            chunks: Retrieved candidate chunks.

        Returns:
            Contradicted assessment mapping.
        """
        debt_index = next(index for index, item in enumerate(chunks) if "Debt" in item.chunk.text)
        return _assessment("CONTRADICTED", chunks, evidence_against=(debt_index,))

    def insufficient(_: str, chunks):
        """Report missing evidence without treating silence as contradiction.

        Args:
            _: Ignored claim.
            chunks: Retrieved candidate chunks.

        Returns:
            Insufficient-evidence assessment mapping.
        """
        return _assessment("INSUFFICIENT_EVIDENCE", chunks, missing=("No local filing discusses the asserted condition.",))

    partial_result = verify_sec_claim(directory, claim, lambda query: _embed([query])[0], partial)
    contradicted_result = verify_sec_claim(directory, claim, lambda query: _embed([query])[0], contradicted)
    insufficient_result = verify_sec_claim(directory, claim, lambda query: _embed([query])[0], insufficient)

    assert partial_result.verification is not None and partial_result.verification.verdict == "PARTIALLY_CONFIRMED"
    assert contradicted_result.verification is not None and contradicted_result.verification.verdict == "CONTRADICTED"
    assert insufficient_result.verification is not None
    assert insufficient_result.verification.verdict == "INSUFFICIENT_EVIDENCE"
    assert not insufficient_result.verification.evidence_against


def test_verifier_rejects_unknown_citations_and_unavailable_assessor(tmp_path: Path) -> None:
    """Reject fabricated citations and never create a fallback verdict without an assessor.

    Args:
        tmp_path: Pytest-managed temporary filesystem root.

    Returns:
        None. Assertions verify safe assessor-boundary failures.
    """
    from app.sec.verifier import verify_sec_claim

    directory = _case(tmp_path / "cases")

    def fabricated(_: str, chunks):
        """Return an invalid unknown citation ID.

        Args:
            _: Ignored claim.
            chunks: Retrieved candidates, retained for signature coverage.

        Returns:
            Invalid assessor mapping.
        """
        del chunks
        return {
            "verdict": "CONFIRMED", "confidence": 0.9, "explanation": "Fabricated receipt.",
            "evidence_for_chunk_ids": ["not-a-retrieved-chunk"], "evidence_against_chunk_ids": [],
            "material_sec_facts": {}, "missing_evidence": [], "suggested_document_types": [],
        }

    invalid = verify_sec_claim(directory, "Revenue increased.", lambda query: _embed([query])[0], fabricated)
    unavailable = verify_sec_claim(directory, "Revenue increased.", lambda query: _embed([query])[0], None)

    assert invalid.error is not None and invalid.error.code == "INVALID_ASSESSMENT"
    assert unavailable.error is not None and unavailable.error.code == "ASSESSOR_UNAVAILABLE"


def test_verifier_rejects_malformed_assessment_and_invalid_claim(tmp_path: Path) -> None:
    """Return safe errors for malformed assessor output and unusable claims.

    Args:
        tmp_path: Pytest-managed temporary filesystem root.

    Returns:
        None. Assertions verify public-input and assessor-schema validation.
    """
    from app.sec.verifier import verify_sec_claim

    directory = _case(tmp_path / "cases")
    malformed = verify_sec_claim(directory, "Revenue increased.", lambda query: _embed([query])[0], lambda claim, chunks: {"verdict": "CONFIRMED"})
    invalid_claim = verify_sec_claim(directory, " ", lambda query: _embed([query])[0], lambda claim, chunks: {})

    assert malformed.error is not None and malformed.error.code == "INVALID_ASSESSMENT"
    assert invalid_claim.error is not None and invalid_claim.error.code == "INVALID_INPUT"


def test_verifier_returns_safe_retrieval_failure_and_never_uses_network(tmp_path: Path, monkeypatch) -> None:
    """Report missing local indexes without permitting a network fallback.

    Args:
        tmp_path: Pytest-managed temporary filesystem root.
        monkeypatch: Pytest network-blocking fixture.

    Returns:
        None. Assertions verify local-only failure behavior.
    """
    from app.sec.verifier import verify_sec_claim

    def blocked_network(*args, **kwargs):
        """Fail if any code path attempts a network connection.

        Args:
            *args: Ignored connection arguments.
            **kwargs: Ignored connection keyword arguments.

        Returns:
            None.

        Raises:
            AssertionError: Always, because the verifier must be local-only.
        """
        del args, kwargs
        raise AssertionError("network access is prohibited")

    monkeypatch.setattr("socket.create_connection", blocked_network)
    result = verify_sec_claim(tmp_path / "missing", "Revenue increased.", lambda query: _embed([query])[0], lambda claim, chunks: {})

    assert result.error is not None and result.error.code == "RETRIEVAL_FAILED"
