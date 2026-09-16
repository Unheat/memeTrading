"""Red-phase tests for case-local corpus manifest storage."""

from datetime import date, datetime, timezone

import pytest

from app.sec.schemas import DownloadedDocument, PulledCorpus
from app.storage.cases import (
    StorageError,
    case_path,
    create_case_id,
    allocate_case,
    read_corpus_manifest,
    read_run_manifest,
    write_corpus_manifest,
    write_run_manifest,
)


def _corpus() -> PulledCorpus:
    """Build a valid local corpus fixture without external services."""
    return PulledCorpus(
        corpus_id="XYZ-2026-09-01-001",
        ticker="XYZ",
        cik="123456",
        created_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        documents=(
            DownloadedDocument(
                accession="0000123456-26-000001",
                form="8-K",
                filing_date=date(2026, 9, 1),
                document_name="primary.htm",
                source_url="https://www.sec.gov/Archives/example.htm",
                relative_path="sec/primary.htm",
                sha256="a" * 64,
            ),
        ),
    )


def test_create_case_id_is_deterministic() -> None:
    """Format a validated case identifier consistently."""
    assert create_case_id("xyz", date(2026, 9, 1), 1) == "XYZ-2026-09-01-001"


def test_case_path_is_direct_child_without_creating_directory(tmp_path) -> None:
    """Return a safe child path without creating case storage."""
    target = case_path(tmp_path, "XYZ-2026-09-01-001")

    assert target == tmp_path / "XYZ-2026-09-01-001"
    assert not target.exists()


def test_allocate_case_claims_distinct_directories(tmp_path) -> None:
    """Atomically allocate distinct daily case directories without overwriting."""
    first_id, first_dir = allocate_case(tmp_path, "XYZ", date(2026, 9, 1))
    second_id, second_dir = allocate_case(tmp_path, "XYZ", date(2026, 9, 1))

    assert first_id == "XYZ-2026-09-01-001"
    assert second_id == "XYZ-2026-09-01-002"
    assert first_dir.is_dir() and second_dir.is_dir()


def test_run_manifest_round_trip(tmp_path) -> None:
    """Persist and reload one atomic lifecycle manifest."""
    _, case_directory = allocate_case(tmp_path, "XYZ", date(2026, 9, 1))
    write_run_manifest(case_directory, {"case_id": case_directory.name, "status": "running"})

    assert read_run_manifest(case_directory)["status"] == "running"


def test_manifest_round_trip(tmp_path) -> None:
    """Persist and reload one validated local corpus manifest."""
    case_directory = case_path(tmp_path, "XYZ-2026-09-01-001")
    case_directory.mkdir()

    manifest = write_corpus_manifest(case_directory, _corpus())

    assert manifest == case_directory / "sec" / "corpus-manifest.json"
    assert read_corpus_manifest(case_directory) == _corpus()


def test_read_manifest_rejects_invalid_json(tmp_path) -> None:
    """Convert corrupt local manifest content into a storage error."""
    case_directory = case_path(tmp_path, "XYZ-2026-09-01-001")
    (case_directory / "sec").mkdir(parents=True)
    (case_directory / "sec" / "corpus-manifest.json").write_text("not json")

    with pytest.raises(StorageError, match="invalid"):
        read_corpus_manifest(case_directory)
