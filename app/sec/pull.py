"""Controlled download of explicitly selected SEC documents into one local case."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import os
from pathlib import Path
import re
import time
from typing import Literal
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from app.sec.schemas import DownloadedDocument, FilingMetadata, PulledCorpus
from app.storage.cases import case_path, read_corpus_manifest, write_corpus_manifest


MAX_DOCUMENTS_PER_CORPUS = 10
MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 30
SEC_REQUEST_INTERVAL_SECONDS = 0.11
SEC_IDENTITY_ENV_NAME = "SEC_USER_AGENT"
FILENAME_DIGEST_PREFIX_LENGTH = 12
VALID_ERROR_CODES = frozenset(
    {
        "INVALID_INPUT",
        "INVALID_SELECTION",
        "UNAVAILABLE",
        "SIZE_LIMIT",
        "STORAGE_FAILURE",
        "DEPENDENCY_UNAVAILABLE",
    }
)
SEC_DOCUMENT_DIRECTORY = Path("sec") / "documents"
SEC_HOST_SUFFIX = ".sec.gov"
SAFE_FILENAME_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


class _MissingIdentityError(Exception):
    """Signal absent SEC request identity without exposing environment details."""


class _DocumentTooLargeError(Exception):
    """Signal a source body exceeding the configured local safety limit."""


class _StorageFailure(Exception):
    """Signal a local persistence failure without exposing filesystem details."""


@dataclass(frozen=True)
class SelectedSecDocument:
    """One exact SEC document selected by the outer agent.

    Attributes:
        filing: Previously discovered filing receipt.
        document_name: Primary document or declared exhibit name.
        source_url: Exact HTTPS SEC URL for the selected document.
    """

    filing: FilingMetadata
    document_name: str
    source_url: str


@dataclass(frozen=True)
class PullError:
    """Safe recoverable failure returned by controlled SEC acquisition.

    Attributes:
        code: Stable machine-readable error class.
        message: Safe explanation for a future agent tool.
        retryable: Whether a later retry can reasonably succeed.
    """

    code: Literal[
        "INVALID_INPUT",
        "INVALID_SELECTION",
        "UNAVAILABLE",
        "SIZE_LIMIT",
        "STORAGE_FAILURE",
        "DEPENDENCY_UNAVAILABLE",
    ]
    message: str
    retryable: bool

    def __post_init__(self) -> None:
        """Validate stable failure values.

        Args:
            None.

        Returns:
            None.

        Raises:
            ValueError: If code or message is invalid.
        """
        if self.code not in VALID_ERROR_CODES or not self.message.strip():
            raise ValueError("pull error is invalid")


@dataclass(frozen=True)
class FilingPullResult:
    """Successful local corpus or one recoverable acquisition failure.

    Attributes:
        corpus: Completed local corpus when successful.
        error: Safe failure when acquisition did not complete.
    """

    corpus: PulledCorpus | None = None
    error: PullError | None = None

    def __post_init__(self) -> None:
        """Require exactly one result branch.

        Args:
            None.

        Returns:
            None.

        Raises:
            ValueError: If success and failure branches are ambiguous.
        """
        if (self.corpus is None) == (self.error is None):
            raise ValueError("result must contain exactly one of corpus or error")


def _failure(
    code: Literal[
        "INVALID_INPUT",
        "INVALID_SELECTION",
        "UNAVAILABLE",
        "SIZE_LIMIT",
        "STORAGE_FAILURE",
        "DEPENDENCY_UNAVAILABLE",
    ],
    message: str,
    retryable: bool,
) -> FilingPullResult:
    """Build a safe structured failure result.

    Args:
        code: Stable pull failure code.
        message: Caller-safe explanation.
        retryable: Whether a later retry may work.

    Returns:
        Failure-only result.
    """
    return FilingPullResult(error=PullError(code, message, retryable))


def _is_sec_url(source_url: str) -> bool:
    """Check whether a URL is an HTTPS SEC host URL.

    Args:
        source_url: Candidate remote document URL.

    Returns:
        True only for HTTPS `sec.gov` hosts.
    """
    parsed = urlparse(source_url)
    host = parsed.hostname or ""
    return parsed.scheme == "https" and (host == "sec.gov" or host.endswith(SEC_HOST_SUFFIX))


def _safe_document_name(document_name: str) -> bool:
    """Check that a declared document name cannot create nested paths.

    Args:
        document_name: Candidate SEC document filename.

    Returns:
        True when name is a non-empty single filename.
    """
    return (
        bool(document_name.strip())
        and document_name not in {".", ".."}
        and document_name == Path(document_name).name
        and "\\" not in document_name
    )


def _validate_selections(selections: Iterable[SelectedSecDocument]) -> tuple[SelectedSecDocument, ...]:
    """Validate one-company exact SEC document selections before I/O.

    Args:
        selections: Caller-selected document records.

    Returns:
        Immutable validated selection tuple.

    Raises:
        ValueError: If selections are unsafe, mixed-company, duplicate, or undeclared.
    """
    if isinstance(selections, (str, bytes)):
        raise ValueError("selections must be an iterable of SelectedSecDocument")
    selected = tuple(selections)
    if not selected or len(selected) > MAX_DOCUMENTS_PER_CORPUS:
        raise ValueError("selection count is invalid")
    if not all(isinstance(item, SelectedSecDocument) for item in selected):
        raise ValueError("selection type is invalid")
    company_identity = {(item.filing.ticker, item.filing.cik) for item in selected}
    document_identity = {(item.filing.accession, item.document_name) for item in selected}
    if len(company_identity) != 1 or len(document_identity) != len(selected):
        raise ValueError("selections must be unique and for one company")
    for item in selected:
        declared_documents = {name for name in (item.filing.primary_document, *item.filing.exhibits) if name}
        if (
            not _safe_document_name(item.document_name)
            or not _is_sec_url(item.source_url)
            or (declared_documents and item.document_name not in declared_documents)
        ):
            raise ValueError("selection is not a declared safe SEC document")
    return selected


def _local_filename(selection: SelectedSecDocument) -> str:
    """Produce a deterministic path-safe filename for one selected document.

    Args:
        selection: Valid exact SEC document selection.

    Returns:
        Safe filename retaining a readable sanitized document suffix.
    """
    safe_name = SAFE_FILENAME_PATTERN.sub("_", selection.document_name)
    name_digest = sha256(selection.document_name.encode("utf-8")).hexdigest()[:FILENAME_DIGEST_PREFIX_LENGTH]
    accession = selection.filing.accession.replace("-", "")
    return f"{accession}-{name_digest}-{safe_name}"


def _default_downloader(source_url: str) -> bytes:
    """Download one bounded SEC document using configured declared identity.

    Args:
        source_url: Valid HTTPS SEC source URL.

    Returns:
        Complete document bytes within configured size limit.

    Raises:
        _MissingIdentityError: If SEC user-agent identity is not configured.
        _DocumentTooLargeError: If SEC source exceeds local byte limit.
        OSError: If remote request fails.
    """
    identity = os.environ.get(SEC_IDENTITY_ENV_NAME, "").strip()
    if not identity:
        raise _MissingIdentityError
    request = Request(source_url, headers={"User-Agent": identity, "Accept-Encoding": "gzip, deflate"})
    with urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
        body = response.read(MAX_DOCUMENT_BYTES + 1)
    if len(body) > MAX_DOCUMENT_BYTES:
        raise _DocumentTooLargeError
    return body


def _existing_identical_corpus(case_directory: Path, selections: tuple[SelectedSecDocument, ...]) -> PulledCorpus | None:
    """Return a prior completed corpus only when it exactly matches selections.

    Args:
        case_directory: Existing case directory that may have a manifest.
        selections: Valid requested exact document set.

    Returns:
        Existing validated corpus when each receipt and stored digest matches; otherwise None.

    Raises:
        OSError: If an existing manifest's referenced file cannot be read.
    """
    manifest_path = case_directory / "sec" / "corpus-manifest.json"
    if not manifest_path.exists():
        return None
    corpus = read_corpus_manifest(case_directory)
    requested = {(item.filing.accession, item.document_name, item.source_url) for item in selections}
    existing = {(item.accession, item.document_name, item.source_url) for item in corpus.documents}
    if requested != existing:
        return None
    for document in corpus.documents:
        body = (case_directory / document.relative_path).read_bytes()
        if sha256(body).hexdigest() != document.sha256:
            return None
    return corpus


def _cleanup_created_files(created_files: list[Path], documents_directory: Path) -> None:
    """Remove only paths created by the current failed pull attempt.

    Args:
        created_files: Exact successfully-created document files.
        documents_directory: Directory containing those document files.

    Returns:
        None.
    """
    for path in created_files:
        path.unlink(missing_ok=True)
    try:
        documents_directory.rmdir()
        documents_directory.parent.rmdir()
    except OSError:
        pass


def pull_sec_filings(
    cases_root: Path,
    case_id: str,
    selections: Iterable[SelectedSecDocument],
    downloader: Callable[[str], bytes] | None = None,
) -> FilingPullResult:
    """Download exact selected SEC documents into one complete local corpus.

    Args:
        cases_root: Parent directory for all local investigation cases.
        case_id: Valid direct-child case identifier.
        selections: Exact filing/document records chosen by the outer agent.
        downloader: Optional injected `URL -> bytes` downloader for tests.

    Returns:
        Completed `PulledCorpus` or safe recoverable pull failure. No partial corpus is
        retained for files created by a failed invocation.
    """
    try:
        selected = _validate_selections(selections)
    except TypeError:
        return _failure("INVALID_INPUT", "Case ID or selected documents are invalid.", False)
    except (AttributeError, ValueError):
        return _failure("INVALID_SELECTION", "Selected SEC documents are invalid.", False)
    try:
        directory = case_path(cases_root, case_id)
    except (AttributeError, TypeError, ValueError):
        return _failure("INVALID_INPUT", "Case ID or selected documents are invalid.", False)

    try:
        directory.parent.mkdir(parents=True, exist_ok=True)
        directory.mkdir(exist_ok=True)
        existing = _existing_identical_corpus(directory, selected)
        if existing is not None:
            return FilingPullResult(corpus=existing)
        if (directory / "sec" / "corpus-manifest.json").exists():
            return _failure("INVALID_SELECTION", "Case already contains a different SEC corpus.", False)
    except (OSError, ValueError):
        return _failure("STORAGE_FAILURE", "Local SEC corpus storage is unavailable.", True)

    documents_directory = directory / SEC_DOCUMENT_DIRECTORY
    created_files: list[Path] = []
    fetch = downloader or _default_downloader
    documents: list[DownloadedDocument] = []
    try:
        documents_directory.mkdir(parents=True, exist_ok=True)
        for selection in selected:
            target = documents_directory / _local_filename(selection)
            if target.exists():
                raise ValueError("target document already exists without matching manifest")
            if downloader is None:
                time.sleep(SEC_REQUEST_INTERVAL_SECONDS)
            body = fetch(selection.source_url)
            if not isinstance(body, bytes):
                raise TypeError("downloader must return bytes")
            if len(body) > MAX_DOCUMENT_BYTES:
                raise _DocumentTooLargeError
            try:
                target.write_bytes(body)
            except OSError as error:
                raise _StorageFailure from error
            created_files.append(target)
            documents.append(
                DownloadedDocument(
                    accession=selection.filing.accession,
                    form=selection.filing.form,
                    filing_date=selection.filing.filing_date,
                    document_name=selection.document_name,
                    source_url=selection.source_url,
                    relative_path=str(target.relative_to(directory)),
                    sha256=sha256(body).hexdigest(),
                )
            )
        corpus = PulledCorpus(
            corpus_id=case_id,
            ticker=selected[0].filing.ticker,
            cik=selected[0].filing.cik,
            created_at=datetime.now(timezone.utc),
            documents=tuple(documents),
        )
        try:
            write_corpus_manifest(directory, corpus)
        except OSError as error:
            raise _StorageFailure from error
        return FilingPullResult(corpus=corpus)
    except _StorageFailure:
        _cleanup_created_files(created_files, documents_directory)
        return _failure("STORAGE_FAILURE", "Local SEC corpus storage is unavailable.", True)
    except _MissingIdentityError:
        _cleanup_created_files(created_files, documents_directory)
        return _failure("DEPENDENCY_UNAVAILABLE", "SEC request identity is not configured.", False)
    except _DocumentTooLargeError:
        _cleanup_created_files(created_files, documents_directory)
        return _failure("SIZE_LIMIT", "Selected SEC document exceeds the configured size limit.", False)
    except (OSError, ValueError):
        _cleanup_created_files(created_files, documents_directory)
        return _failure("UNAVAILABLE", "Selected SEC document is currently unavailable.", True)
    except (AttributeError, TypeError):
        _cleanup_created_files(created_files, documents_directory)
        return _failure("STORAGE_FAILURE", "SEC pull could not be stored safely.", True)
