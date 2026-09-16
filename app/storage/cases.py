"""Filesystem-only persistence for case-local research artifacts and manifests."""
from __future__ import annotations

from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from typing import Any, Mapping

from app.sec.schemas import PulledCorpus


CASE_ID_PATTERN = re.compile(r"^[A-Z]{1,10}-\d{4}-\d{2}-\d{2}-\d{3}$")
MANIFEST_FILENAME = "corpus-manifest.json"
RUN_MANIFEST_FILENAME = "run-manifest.json"
SEC_DIRECTORY_NAME = "sec"
RUN_MANIFEST_VERSION = 1
RUN_STATUSES = frozenset({"running", "completed", "failed", "cancelled"})


class StorageError(ValueError):
    """Raised when a local manifest cannot be safely read or allocated."""


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


CANDIDATE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


def case_path(cases_root: Path | str, case_id: str) -> Path:
    """Return direct case or candidate directory path without creating it.

    Args:
        cases_root: Configured parent directory for all cases.
        case_id: Valid normalized case identifier or candidate sub-path.

    Returns:
        Direct child path beneath `cases_root` or isolated candidate directory.

    Raises:
        ValueError: If case ID is invalid or path containment cannot be established.
    """
    root = Path(cases_root).resolve()
    clean_id = case_id.strip()
    if "/candidates/" in clean_id:
        base_id, cand_id = clean_id.split("/candidates/", 1)
        base_id = base_id.strip()
        cand_id = cand_id.strip()
        if not (CASE_ID_PATTERN.fullmatch(base_id) or CANDIDATE_ID_PATTERN.fullmatch(base_id)) or not CANDIDATE_ID_PATTERN.fullmatch(cand_id):
            raise ValueError("case_id or candidate_id is invalid")
        base_dir = (root / base_id).resolve()
        target = (base_dir / "candidates" / cand_id).resolve()
        try:
            target.relative_to(base_dir)
        except ValueError as exc:
            raise ValueError("candidate directory escapes base case") from exc
        return target

    if not CASE_ID_PATTERN.fullmatch(clean_id):
        raise ValueError("case_id is invalid")
    target = (root / clean_id).resolve()
    if target.parent != root:
        raise ValueError("case_id must resolve to a direct cases_root child")
    return target


def allocate_case(cases_root: Path | str, ticker: str, case_date: date | None = None) -> tuple[str, Path]:
    """Atomically claim a unique daily case directory.

    Args:
        cases_root: Parent directory for all cases.
        ticker: Target ticker, normalized to a safe case identifier.
        case_date: Date to encode, defaulting to today.

    Returns:
        Claimed case ID and newly created direct child directory.

    Raises:
        StorageError: If all allowed daily sequence IDs already exist.
    """
    root = Path(cases_root)
    root.mkdir(parents=True, exist_ok=True)
    normalized_ticker = ticker if ticker.isalpha() and 1 <= len(ticker) <= 10 else "RESEARCH"
    today = case_date or date.today()
    for sequence in range(1, 1000):
        case_id = create_case_id(normalized_ticker, today, sequence)
        directory = case_path(root, case_id)
        try:
            directory.mkdir()
        except FileExistsError:
            continue
        return case_id, directory
    raise StorageError("case sequence exhausted for date and ticker")


def _atomic_json_write(path: Path, payload: Mapping[str, Any]) -> Path:
    """Write a JSON object through a sibling temporary file.

    Args:
        path: Destination file beneath an existing directory.
        payload: JSON-safe object to persist.

    Returns:
        Destination path after atomic replacement.
    """
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as temporary:
        json.dump(payload, temporary, indent=2, sort_keys=True, default=str)
        temporary.write("\n")
        temporary_path = Path(temporary.name)
    try:
        os.replace(temporary_path, path)
    except OSError:
        temporary_path.unlink(missing_ok=True)
        raise
    return path


def write_run_manifest(case_directory: Path, manifest: Mapping[str, Any]) -> Path:
    """Atomically persist one validated run lifecycle manifest.

    Args:
        case_directory: Existing claimed case directory.
        manifest: JSON-safe lifecycle details including a valid terminal or running status.

    Returns:
        Path to `run-manifest.json`.

    Raises:
        ValueError: If directory or lifecycle status is invalid.
    """
    directory = Path(case_directory)
    if not directory.is_dir():
        raise ValueError("case_directory must be an existing directory")
    status = manifest.get("status")
    if status not in RUN_STATUSES:
        raise ValueError("run manifest status is invalid")
    payload = dict(manifest)
    payload.setdefault("version", RUN_MANIFEST_VERSION)
    payload.setdefault("updated_at", datetime.now(timezone.utc).isoformat())
    return _atomic_json_write(directory / RUN_MANIFEST_FILENAME, payload)


def read_run_manifest(case_directory: Path) -> dict[str, Any]:
    """Load and validate a local run lifecycle manifest.

    Args:
        case_directory: Existing case directory containing `run-manifest.json`.

    Returns:
        Parsed lifecycle manifest.

    Raises:
        StorageError: If manifest is absent, invalid JSON, or invalid lifecycle data.
    """
    try:
        with (Path(case_directory) / RUN_MANIFEST_FILENAME).open(encoding="utf-8") as manifest_file:
            payload = json.load(manifest_file)
        if not isinstance(payload, dict) or payload.get("status") not in RUN_STATUSES:
            raise ValueError("invalid lifecycle status")
        return payload
    except (FileNotFoundError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise StorageError("run manifest is invalid") from error


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
    return _atomic_json_write(sec_directory / MANIFEST_FILENAME, corpus.to_dict())


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
