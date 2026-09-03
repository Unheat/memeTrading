"""Red-phase tests for SEC data contracts."""

from datetime import date, datetime, timezone

import pytest

from app.sec.schemas import (
    DownloadedDocument,
    FilingMetadata,
    PulledCorpus,
    SECVerification,
    SecEvidence,
)


def test_filing_metadata_normalizes_ticker_and_cik() -> None:
    """Normalize ticker and CIK while preserving valid filing metadata."""
    filing = FilingMetadata(
        ticker="xyz",
        cik="0000123456",
        form="8-K",
        filing_date=date(2026, 9, 1),
        accession="0000123456-26-000001",
        filing_url="https://www.sec.gov/Archives/example.htm",
    )

    assert filing.ticker == "XYZ"
    assert filing.cik == "123456"


@pytest.mark.parametrize("relative_path", ["/tmp/filing.htm", "../filing.htm"])
def test_downloaded_document_rejects_unsafe_relative_path(relative_path: str) -> None:
    """Reject absolute and traversal document paths."""
    with pytest.raises(ValueError, match="relative_path"):
        DownloadedDocument(
            accession="0000123456-26-000001",
            form="8-K",
            filing_date=date(2026, 9, 1),
            document_name="primary.htm",
            source_url="https://www.sec.gov/Archives/example.htm",
            relative_path=relative_path,
            sha256="a" * 64,
        )


def test_pulled_corpus_derives_unique_accessions() -> None:
    """Expose accessions from documents rather than caller-supplied state."""
    document = DownloadedDocument(
        accession="0000123456-26-000001",
        form="8-K",
        filing_date=date(2026, 9, 1),
        document_name="primary.htm",
        source_url="https://www.sec.gov/Archives/example.htm",
        relative_path="sec/primary.htm",
        sha256="a" * 64,
    )
    exhibit = DownloadedDocument(
        accession="0000123456-26-000001",
        form="8-K",
        filing_date=date(2026, 9, 1),
        document_name="exhibit.htm",
        source_url="https://www.sec.gov/Archives/exhibit.htm",
        relative_path="sec/exhibit.htm",
        sha256="b" * 64,
    )

    corpus = PulledCorpus(
        corpus_id="XYZ-2026-09-01-001",
        ticker="XYZ",
        cik="123456",
        created_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        documents=(document, exhibit),
    )

    assert corpus.accessions == ("0000123456-26-000001",)


def test_verification_requires_evidence_for_confirmed_verdict() -> None:
    """Reject a confirmed verdict without supporting SEC evidence."""
    with pytest.raises(ValueError, match="evidence_for"):
        SECVerification(
            claim="XYZ signed a binding agreement.",
            verdict="CONFIRMED",
            confidence=0.9,
            explanation="The filing supports the claim.",
            evidence_for=(),
            evidence_against=(),
            material_sec_facts={},
            missing_evidence=(),
            suggested_document_types=(),
        )


def test_verification_round_trips_nested_evidence() -> None:
    """Preserve a cited verifier response through JSON-safe dictionaries."""
    evidence = SecEvidence(
        accession="0000123456-26-000001",
        form="8-K",
        filing_date=date(2026, 9, 1),
        document="primary.htm",
        quote="The parties entered into an agreement.",
        source_url="https://www.sec.gov/Archives/example.htm",
    )
    response = SECVerification(
        claim="XYZ signed an agreement.",
        verdict="CONFIRMED",
        confidence=0.9,
        explanation="The local filing states that the parties entered an agreement.",
        evidence_for=(evidence,),
        evidence_against=(),
        material_sec_facts={"binding": True},
        missing_evidence=(),
        suggested_document_types=(),
    )

    assert SECVerification.from_dict(response.to_dict()) == response
