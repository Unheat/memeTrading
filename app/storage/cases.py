"""Filesystem-only persistence for case-local SEC corpus manifests."""

from __future__ import annotations

from datetime import date
import json
import os
from pathlib import Path
import re
from tempfile import NamedTemporaryFile

from app.sec.schemas import PulledCorpus


CASE_ID_PATTERN = re.compile(r"^[A-Z]{1,10}-\d{4}-\d{2}-\d{2}-\d{3}$")
MANIFEST_FILENAME = "corpus-manifest.json"
SEC_DIRECTORY_NAME = "sec"


class StorageError(ValueError):
    """Raised when a local corpus manifest cannot be safely read."""


def create_case_id(ticker: str, case_date: date, sequence: int) -> str:
    """Create one normalized case identifier.

    Args:
        ticker: Case ticker, with any letter case accepted.
        case_date: Investigation date.
        sequence: Per-date case sequence from 1 through 999.

    Returns:
        Identifier in `TICKER-YYYY-MM-DD-NNN` form.

    Raises:
        ValueError: If ticker or sequence is invalid.
    """
    normalized_ticker = ticker.strip().upper()
    if not normalized_ticker.isalpha() or not 1 <= len(normalized_ticker) <= 10:
        raise ValueError("ticker must contain 1 to 10 letters")
    if not 1 <= sequence <= 999:
        raise ValueError("sequence must be between 1 and 999")
    return f"{normalized_ticker}-{case_date.isoformat()}-{sequence:03d}"


def case_path(cases_root: Path, case_id: str) -> Path:
    """Return the direct case directory path without creating it.

    Args:
        cases_root: Configured parent directory for all cases.
        case_id: Valid normalized case identifier.

    Returns:
        Direct child path beneath `cases_root`.

    Raises:
        ValueError: If case ID is invalid or path containment cannot be established.
    """
    if not CASE_ID_PATTERN.fullmatch(case_id):
        raise ValueError("case_id is invalid")
    root = Path(cases_root).resolve()
    target = (root / case_id).resolve()
    if target.parent != root:
        raise ValueError("case_id must resolve to a direct cases_root child")
    return target


def write_corpus_manifest(case_directory: Path, corpus: PulledCorpus) -> Path:
    """Atomically persist a validated corpus manifest under one case directory.

    Args:
        case_directory: Existing case directory.
        corpus: Validated local corpus to serialize.

    Returns:
        Manifest path at `sec/corpus-manifest.json`.

    Raises:
        ValueError: If case directory does not exist or is not a directory.
        OSError: If local storage write fails.
    """
    directory = Path(case_directory)
    if not directory.is_dir():
        raise ValueError("case_directory must be an existing directory")
    sec_directory = directory / SEC_DIRECTORY_NAME
    sec_directory.mkdir(exist_ok=True)
    manifest_path = sec_directory / MANIFEST_FILENAME
    with NamedTemporaryFile("w", encoding="utf-8", dir=sec_directory, delete=False) as temporary:
        json.dump(corpus.to_dict(), temporary, indent=2, sort_keys=True)
        temporary.write("\n")
        temporary_path = Path(temporary.name)
    try:
        os.replace(temporary_path, manifest_path)
    except OSError:
        temporary_path.unlink(missing_ok=True)
        raise
    return manifest_path


def read_corpus_manifest(case_directory: Path) -> PulledCorpus:
    """Load and validate one local corpus manifest without network access.

    Args:
        case_directory: Case directory containing the manifest.

    Returns:
        Validated local corpus.

    Raises:
        StorageError: If manifest is missing, invalid JSON, or violates contracts.
    """
    manifest_path = Path(case_directory) / SEC_DIRECTORY_NAME / MANIFEST_FILENAME
    try:
        with manifest_path.open(encoding="utf-8") as manifest_file:
            payload = json.load(manifest_file)
        return PulledCorpus.from_dict(payload)
    except FileNotFoundError as error:
        raise StorageError("corpus manifest is missing") from error
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        raise StorageError("corpus manifest is invalid") from error
