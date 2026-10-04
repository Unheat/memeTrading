"""Tests for local SEC corpus text preparation."""

from datetime import date
from pathlib import Path

from app.sec.pull import SelectedSecDocument, pull_sec_filings
from app.sec.schemas import FilingMetadata


CASE_ID = "XYZ-2026-09-02-001"
TEXT_URL = "https://www.sec.gov/Archives/edgar/data/1/000000000026000002/report.txt"
HTML_URL = "https://www.sec.gov/Archives/edgar/data/1/000000000026000002/exhibit.html"


def _filing(document_name: str = "report.txt", exhibits: tuple[str, ...] = ()) -> FilingMetadata:
    """Create valid filing metadata for local corpus fixtures.

    Args:
        document_name: Declared primary document name.
        exhibits: Declared exhibit document names.

    Returns:
        Valid filing metadata for one selected SEC filing.
    """
    return FilingMetadata(
        ticker="XYZ",
        cik="1",
        form="8-K",
        filing_date=date(2026, 9, 2),
        accession="0000000000-26-000002",
        filing_url=TEXT_URL,
        primary_document=document_name,
        exhibits=exhibits,
    )


def _pull_case(root: Path, selections: tuple[SelectedSecDocument, ...], bodies: dict[str, bytes]) -> Path:
    """Create a completed local pull corpus from fake SEC source bytes.

    Args:
        root: Temporary cases-root directory.
        selections: Exact selected filing documents.
        bodies: Source URL to byte content mapping.

    Returns:
        Existing case directory containing a corpus manifest.
    """
    result = pull_sec_filings(root, CASE_ID, selections, lambda url: bodies[url])
    assert result.error is None
    return root / CASE_ID


def test_prepare_plaintext_chunks_with_receipts(tmp_path: Path) -> None:
    """Create deterministic citation-preserving chunks for local plaintext.

    Args:
        tmp_path: Pytest-managed isolated filesystem root.

    Returns:
        None. Assertions verify chunk text and receipt metadata.
    """
    from app.sec.corpus import prepare_sec_corpus

    selection = SelectedSecDocument(_filing(), "report.txt", TEXT_URL)
    case_directory = _pull_case(tmp_path / "cases", (selection,), {TEXT_URL: b"Revenue rose sharply. Cash was $20 million."})

    result = prepare_sec_corpus(case_directory)

    assert result.error is None
    assert result.chunks
    chunk = result.chunks[0]
    assert chunk.text == "Revenue rose sharply. Cash was $20 million."
    assert chunk.accession == selection.filing.accession
    assert chunk.document_name == "report.txt"
    assert chunk.start_offset == 0
    assert chunk.end_offset == len(chunk.text)
    assert result.artifact_path == case_directory / "sec" / "index" / "chunks.jsonl"
    assert result.artifact_path.exists()


def test_prepare_extracts_visible_html_and_ignores_script_style(tmp_path: Path) -> None:
    """Extract visible SEC HTML text without script or style payloads.

    Args:
        tmp_path: Pytest-managed isolated filesystem root.

    Returns:
        None. Assertions verify visible-text-only extraction.
    """
    from app.sec.corpus import prepare_sec_corpus

    filing = _filing("report.txt", ("exhibit.html",))
    selections = (
        SelectedSecDocument(filing, "report.txt", TEXT_URL),
        SelectedSecDocument(filing, "exhibit.html", HTML_URL),
    )
    case_directory = _pull_case(
        tmp_path / "cases",
        selections,
        {
            TEXT_URL: b"Filing cover text.",
            HTML_URL: b"<html><style>hidden-style</style><body>Binding <b>agreement</b><script>hidden-script</script></body></html>",
        },
    )

    result = prepare_sec_corpus(case_directory)

    assert result.error is None
    html_text = next(chunk.text for chunk in result.chunks if chunk.document_name == "exhibit.html")
    assert html_text == "Binding agreement"


def test_prepare_rejects_changed_or_missing_receipt_file(tmp_path: Path) -> None:
    """Reject a changed or deleted local document before indexing.

    Args:
        tmp_path: Pytest-managed isolated filesystem root.

    Returns:
        None. Assertions verify receipt digest enforcement.
    """
    from app.sec.corpus import prepare_sec_corpus

    selection = SelectedSecDocument(_filing(), "report.txt", TEXT_URL)
    case_directory = _pull_case(tmp_path / "cases", (selection,), {TEXT_URL: b"original"})
    document_path = next((case_directory / "sec" / "documents").iterdir())
    document_path.write_bytes(b"changed")

    result = prepare_sec_corpus(case_directory)

    assert result.chunks == ()
    assert result.error is not None and result.error.code == "CORRUPT_CORPUS"
    assert not (case_directory / "sec" / "index" / "chunks.jsonl").exists()


def test_prepare_rejects_unsupported_extension(tmp_path: Path) -> None:
    """Report unsupported local SEC formats instead of silently skipping them.

    Args:
        tmp_path: Pytest-managed isolated filesystem root.

    Returns:
        None. Assertions verify explicit format failure.
    """
    from app.sec.corpus import prepare_sec_corpus

    selection = SelectedSecDocument(_filing("report.pdf"), "report.pdf", TEXT_URL)
    case_directory = _pull_case(tmp_path / "cases", (selection,), {TEXT_URL: b"not parsed"})

    result = prepare_sec_corpus(case_directory)

    assert result.error is not None and result.error.code == "UNSUPPORTED_DOCUMENT"


def test_prepare_creates_nonempty_overlapping_long_document_chunks(tmp_path: Path) -> None:
    """Split long normalized filing text with stable non-empty overlap.

    Args:
        tmp_path: Pytest-managed isolated filesystem root.

    Returns:
        None. Assertions verify chunk boundaries and receipt retention.
    """
    from app.sec.corpus import CHUNK_OVERLAP_CHARACTERS, prepare_sec_corpus

    selection = SelectedSecDocument(_filing(), "report.txt", TEXT_URL)
    case_directory = _pull_case(tmp_path / "cases", (selection,), {TEXT_URL: ("word " * 600).encode("utf-8")})

    result = prepare_sec_corpus(case_directory)

    assert result.error is None
    assert len(result.chunks) > 1
    assert all(chunk.text and chunk.accession == selection.filing.accession for chunk in result.chunks)
    assert result.chunks[1].start_offset == result.chunks[0].end_offset - CHUNK_OVERLAP_CHARACTERS


def test_prepare_reuses_identical_chunk_artifact(tmp_path: Path) -> None:
    """Return an existing matching artifact unchanged on repeated preparation.

    Args:
        tmp_path: Pytest-managed isolated filesystem root.

    Returns:
        None. Assertions verify idempotent artifact reuse.
    """
    from app.sec.corpus import prepare_sec_corpus

    selection = SelectedSecDocument(_filing(), "report.txt", TEXT_URL)
    case_directory = _pull_case(tmp_path / "cases", (selection,), {TEXT_URL: b"same local SEC text"})

    first = prepare_sec_corpus(case_directory)
    second = prepare_sec_corpus(case_directory)

    assert first.error is None
    assert second.error is None
    assert first.chunks == second.chunks
    assert first.artifact_path == second.artifact_path


def test_prepare_tags_sections_and_preserves_markdown_tables(tmp_path: Path) -> None:
    """Stamp section labels and keep pipe tables for a structured 10-K document.

    Args:
        tmp_path: Pytest-managed isolated filesystem root.

    Returns:
        None. Assertions verify section tagging, table preservation, and offsets.
    """
    from app.sec.corpus import prepare_sec_corpus

    tenk_url = "https://www.sec.gov/Archives/edgar/data/1/000000000026000002/tenk.htm"
    filing = FilingMetadata(
        ticker="XYZ",
        cik="1",
        form="10-K",
        filing_date=date(2026, 9, 2),
        accession="0000000000-26-000002",
        filing_url=tenk_url,
        primary_document="tenk.htm",
        exhibits=(),
    )
    html = (
        b"<html><body>"
        b"<h1>Item 1. Business</h1><p>Acme operates segments.</p>"
        b"<table><tr><th>Segment</th><th>FY2025 Revenue</th></tr>"
        b"<tr><td>Widgets</td><td>$15,200</td></tr></table>"
        b"<h1>Item 1A. Risk Factors</h1><p>Sole supplier concentration risk.</p>"
        b"</body></html>"
    )
    selection = SelectedSecDocument(filing, "tenk.htm", tenk_url)
    case_directory = _pull_case(tmp_path / "cases", (selection,), {tenk_url: html})

    result = prepare_sec_corpus(case_directory)

    assert result.error is None
    assert result.chunks
    sections = {chunk.section for chunk in result.chunks}
    assert "Item 1 - Business" in sections
    assert "Item 1A - Risk Factors" in sections
    table_chunk = next(chunk for chunk in result.chunks if "Segment" in chunk.text)
    assert "| Segment | FY2025 Revenue |" in table_chunk.text
    assert "| Widgets | $15,200 |" in table_chunk.text
    for chunk in result.chunks:
        assert chunk.end_offset - chunk.start_offset == len(chunk.text)


def test_chunk_from_dict_accepts_legacy_payload_without_section() -> None:
    """Load persisted chunks written before the section field existed.

    Args:
        None.

    Returns:
        None. Assertions verify legacy artifact compatibility.
    """
    from app.sec.corpus import CorpusChunk

    legacy = {
        "chunk_id": "0000000000-26-000002-0-abc",
        "ordinal": 0,
        "accession": "0000000000-26-000002",
        "form": "8-K",
        "filing_date": "2026-09-02",
        "document_name": "report.txt",
        "source_url": TEXT_URL,
        "relative_path": "sec/documents/report.txt",
        "start_offset": 0,
        "end_offset": 12,
        "text": "Legacy text.",
    }

    chunk = CorpusChunk.from_dict(legacy)

    assert chunk.text == "Legacy text."
    assert chunk.section is None
