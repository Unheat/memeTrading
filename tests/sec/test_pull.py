"""Tests for controlled case-local SEC document acquisition."""

from datetime import date
from pathlib import Path

from app.sec.schemas import FilingMetadata


CASE_ID = "XYZ-2026-09-01-001"
SOURCE_URL = "https://www.sec.gov/Archives/edgar/data/1/000000000026000001/report.htm"
EXHIBIT_URL = "https://www.sec.gov/Archives/edgar/data/1/000000000026000001/exhibit.htm"


def _filing(**overrides: object) -> FilingMetadata:
    """Create valid selected-filing metadata for pull tests.

    Args:
        **overrides: Receipt fields replacing default values.

    Returns:
        Validated filing metadata fixture.
    """
    values = {
        "ticker": "XYZ",
        "cik": "1",
        "form": "8-K",
        "filing_date": date(2026, 9, 1),
        "accession": "0000000000-26-000001",
        "filing_url": SOURCE_URL,
        "primary_document": "report.htm",
        "exhibits": ("exhibit.htm",),
    }
    values.update(overrides)
    return FilingMetadata(**values)


def _selection(document_name: str = "report.htm", source_url: str = SOURCE_URL, **filing_overrides: object):
    """Create a selected SEC document after the pull module exists.

    Args:
        document_name: Explicit selected document filename.
        source_url: Exact SEC source URL for selected file.
        **filing_overrides: Receipt-field overrides for the parent filing.

    Returns:
        Selected SEC document fixture.
    """
    from app.sec.pull import SelectedSecDocument

    return SelectedSecDocument(_filing(**filing_overrides), document_name, source_url)


def test_pull_writes_receipts_documents_and_manifest(tmp_path: Path) -> None:
    """Pull one selected document into a readable case-local corpus.

    Args:
        tmp_path: Pytest-managed isolated filesystem root.

    Returns:
        None. Assertions verify complete acquisition output.
    """
    from app.sec.pull import pull_sec_filings
    from app.storage.cases import read_corpus_manifest

    result = pull_sec_filings(tmp_path / "cases", CASE_ID, (_selection(),), lambda _: b"filing body")

    assert result.error is None
    assert result.corpus is not None
    document = result.corpus.documents[0]
    assert document.document_name == "report.htm"
    assert document.sha256 == "206ca2609df1ab0a81b3e42779700bd5bd17c67705ccf1905aff998cce884507"
    assert (tmp_path / "cases" / CASE_ID / document.relative_path).read_bytes() == b"filing body"
    assert read_corpus_manifest(tmp_path / "cases" / CASE_ID) == result.corpus


def test_pull_rejects_invalid_exact_selection(tmp_path: Path) -> None:
    """Reject undeclared document names before downloader use.

    Args:
        tmp_path: Pytest-managed isolated filesystem root.

    Returns:
        None. Assertions verify safe non-retryable failure.
    """
    from app.sec.pull import pull_sec_filings

    result = pull_sec_filings(
        tmp_path / "cases", CASE_ID, (_selection("not-listed.htm"),), lambda _: (_ for _ in ()).throw(AssertionError())
    )

    assert result.corpus is None
    assert result.error is not None
    assert result.error.code == "INVALID_SELECTION"


def test_pull_rejects_mixed_company_and_non_sec_source(tmp_path: Path) -> None:
    """Reject mixed-company or non-SEC selections before any network action.

    Args:
        tmp_path: Pytest-managed isolated filesystem root.

    Returns:
        None. Assertions verify selection-boundary protection.
    """
    from app.sec.pull import pull_sec_filings

    mixed = (_selection(), _selection(ticker="OTHER", cik="2"))
    duplicate = (_selection(), _selection())
    mixed_result = pull_sec_filings(tmp_path / "mixed", CASE_ID, mixed, lambda _: b"unused")
    duplicate_result = pull_sec_filings(tmp_path / "duplicate", CASE_ID, duplicate, lambda _: b"unused")
    non_sec_result = pull_sec_filings(
        tmp_path / "non-sec", CASE_ID, (_selection(source_url="https://example.com/report.htm"),), lambda _: b"unused"
    )

    assert mixed_result.error is not None and mixed_result.error.code == "INVALID_SELECTION"
    assert duplicate_result.error is not None and duplicate_result.error.code == "INVALID_SELECTION"
    assert non_sec_result.error is not None and non_sec_result.error.code == "INVALID_SELECTION"


def test_pull_rejects_unsafe_declared_document_name(tmp_path: Path) -> None:
    """Reject a declared document name that could escape the document directory.

    Args:
        tmp_path: Pytest-managed isolated filesystem root.

    Returns:
        None. Assertions verify nested path prevention.
    """
    from app.sec.pull import pull_sec_filings

    result = pull_sec_filings(
        tmp_path / "cases",
        CASE_ID,
        (_selection("../escape.htm", primary_document="../escape.htm"),),
        lambda _: b"unused",
    )

    assert result.error is not None and result.error.code == "INVALID_SELECTION"


def test_pull_cleans_up_after_partial_source_failure(tmp_path: Path) -> None:
    """Remove invocation-created files when later selected source fails.

    Args:
        tmp_path: Pytest-managed isolated filesystem root.

    Returns:
        None. Assertions verify no partial corpus remains visible.
    """
    from app.sec.pull import pull_sec_filings

    def downloader(url: str) -> bytes:
        """Return first document bytes and fail second source request.

        Args:
            url: Requested source URL.

        Returns:
            Bytes for the primary document.

        Raises:
            OSError: For the simulated unavailable exhibit.
        """
        if url == SOURCE_URL:
            return b"primary"
        raise OSError("source unavailable")

    result = pull_sec_filings(
        tmp_path / "cases", CASE_ID, (_selection(), _selection("exhibit.htm", EXHIBIT_URL)), downloader
    )

    assert result.corpus is None
    assert result.error is not None and result.error.code == "UNAVAILABLE"
    assert not (tmp_path / "cases" / CASE_ID / "sec" / "documents").exists()
    assert not (tmp_path / "cases" / CASE_ID / "sec" / "corpus-manifest.json").exists()


def test_pull_rejects_oversize_source_without_writing(tmp_path: Path) -> None:
    """Return a size-limit result and leave no local document.

    Args:
        tmp_path: Pytest-managed isolated filesystem root.

    Returns:
        None. Assertions verify bounded source handling.
    """
    from app.sec.pull import MAX_DOCUMENT_BYTES, pull_sec_filings

    result = pull_sec_filings(tmp_path / "cases", CASE_ID, (_selection(),), lambda _: b"x" * (MAX_DOCUMENT_BYTES + 1))

    assert result.corpus is None
    assert result.error is not None and result.error.code == "SIZE_LIMIT"
    assert not (tmp_path / "cases" / CASE_ID / "sec" / "documents").exists()


def test_pull_reuses_matching_document_without_redownloading(tmp_path: Path) -> None:
    """Reuse an identical completed document on an idempotent repeat pull.

    Args:
        tmp_path: Pytest-managed isolated filesystem root.

    Returns:
        None. Assertions verify downloader is skipped on repeat.
    """
    from app.sec.pull import pull_sec_filings

    root = tmp_path / "cases"
    first = pull_sec_filings(root, CASE_ID, (_selection(),), lambda _: b"same source")
    second = pull_sec_filings(root, CASE_ID, (_selection(),), lambda _: (_ for _ in ()).throw(AssertionError()))

    assert first.error is None
    assert second.error is None
    assert first.corpus == second.corpus
