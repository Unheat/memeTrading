"""Tests for case-local SEC hybrid retrieval."""

from datetime import date
from pathlib import Path

from app.sec.corpus import prepare_sec_corpus
from app.sec.pull import SelectedSecDocument, pull_sec_filings
from app.sec.schemas import FilingMetadata


CASE_ID = "XYZ-2026-09-02-002"
PRIMARY_URL = "https://www.sec.gov/Archives/edgar/data/1/000000000026000003/report.txt"
EXHIBIT_URL = "https://www.sec.gov/Archives/edgar/data/1/000000000026000003/exhibit.txt"


def _case(root: Path, primary: bytes, exhibit: bytes | None = None) -> Path:
    """Create and prepare one local SEC corpus for retrieval tests.

    Args:
        root: Temporary cases root.
        primary: Primary filing bytes.
        exhibit: Optional exhibit bytes.

    Returns:
        Prepared case directory.
    """
    filing = FilingMetadata(
        ticker="XYZ", cik="1", form="8-K", filing_date=date(2026, 9, 2),
        accession="0000000000-26-000003", filing_url=PRIMARY_URL,
        primary_document="report.txt", exhibits=("exhibit.txt",) if exhibit is not None else (),
    )
    selections = [SelectedSecDocument(filing, "report.txt", PRIMARY_URL)]
    bodies = {PRIMARY_URL: primary}
    if exhibit is not None:
        selections.append(SelectedSecDocument(filing, "exhibit.txt", EXHIBIT_URL))
        bodies[EXHIBIT_URL] = exhibit
    result = pull_sec_filings(root, CASE_ID, tuple(selections), lambda url: bodies[url])
    assert result.error is None
    directory = root / CASE_ID
    assert prepare_sec_corpus(directory).error is None
    return directory


def _embed(texts: list[str]) -> list[list[float]]:
    """Return deterministic local vectors based on finance keywords.

    Args:
        texts: Chunk or query texts to embed.

    Returns:
        Two-dimensional deterministic vectors.
    """
    return [[float("revenue" in text.lower()), float("debt" in text.lower())] for text in texts]


def test_build_and_search_hybrid_local_index(tmp_path: Path) -> None:
    """Build a local FAISS index and return receipt-preserving hybrid results.

    Args:
        tmp_path: Pytest-managed isolated filesystem root.

    Returns:
        None. Assertions verify local index and fused search output.
    """
    from app.sec.retrieval import build_sec_index, search_sec_corpus

    directory = _case(tmp_path / "cases", b"Revenue increased.", b"Debt remains outstanding.")
    built = build_sec_index(directory, _embed)
    found = search_sec_corpus(directory, "debt revenue", lambda query: _embed([query])[0], top_k=2)

    assert built.error is None
    assert built.index_path is not None and built.index_path.exists()
    assert found.error is None
    assert {item.chunk.document_name for item in found.results} == {"report.txt", "exhibit.txt"}
    assert all(item.rrf_score > 0 and item.rerank_status == "NOT_APPLIED" for item in found.results)


def test_search_keeps_duplicate_text_as_distinct_chunk_ids(tmp_path: Path) -> None:
    """Keep distinct filing receipts when source text happens to be identical.

    Args:
        tmp_path: Pytest-managed isolated filesystem root.

    Returns:
        None. Assertions verify identity is never text equality.
    """
    from app.sec.retrieval import build_sec_index, search_sec_corpus

    directory = _case(tmp_path / "cases", b"Revenue same text.", b"Revenue same text.")
    assert build_sec_index(directory, _embed).error is None
    found = search_sec_corpus(directory, "revenue", lambda query: _embed([query])[0], top_k=2)

    assert found.error is None
    assert len({item.chunk.chunk_id for item in found.results}) == 2


def test_search_uses_injected_reranker_order(tmp_path: Path) -> None:
    """Apply local injected reranker scores without any model/network dependency.

    Args:
        tmp_path: Pytest-managed isolated filesystem root.

    Returns:
        None. Assertions verify rerank score ordering.
    """
    from app.sec.retrieval import build_sec_index, search_sec_corpus

    directory = _case(tmp_path / "cases", b"Revenue increased.", b"Debt remains outstanding.")
    assert build_sec_index(directory, _embed).error is None

    def reranker(query: str, chunks):
        """Force exhibit-first ordering for deterministic reranker coverage.

        Args:
            query: Retrieval query, unused by fixture.
            chunks: Candidate chunk sequence.

        Returns:
            Chunk-ID and score pairs in desired order.
        """
        del query
        return [(chunks[1].chunk_id, 2.0), (chunks[0].chunk_id, 1.0)]

    found = search_sec_corpus(directory, "revenue debt", lambda query: _embed([query])[0], reranker=reranker, top_k=2)

    assert found.error is None
    assert found.results[0].chunk.document_name == "exhibit.txt"
    assert found.results[0].rerank_status == "APPLIED"


def test_build_rejects_invalid_vectors_and_missing_preparation(tmp_path: Path) -> None:
    """Return structured local failures for bad vectors or absent preparation.

    Args:
        tmp_path: Pytest-managed isolated filesystem root.

    Returns:
        None. Assertions verify no raw dependency failure escapes.
    """
    from app.sec.retrieval import build_sec_index

    directory = _case(tmp_path / "cases", b"Revenue increased.")
    invalid = build_sec_index(directory, lambda texts: [[float("nan"), 1.0] for _ in texts])
    missing = build_sec_index(tmp_path / "missing", _embed)

    assert invalid.error is not None and invalid.error.code == "INVALID_VECTOR"
    assert missing.error is not None and missing.error.code == "MISSING_PREPARATION"
