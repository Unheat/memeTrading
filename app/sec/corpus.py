"""Prepare verified case-local SEC documents for later local retrieval."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Literal

from app.sec.schemas import DownloadedDocument, PulledCorpus
from app.storage.cases import StorageError, read_corpus_manifest


CHUNK_CHARACTER_LIMIT = 1200
CHUNK_OVERLAP_CHARACTERS = 200
CHUNK_ID_DIGEST_LENGTH = 16
INDEX_DIRECTORY = Path("sec") / "index"
CHUNKS_FILENAME = "chunks.jsonl"
PREPARATION_MANIFEST_FILENAME = "chunks-manifest.json"
SUPPORTED_SUFFIXES = frozenset({".txt", ".htm", ".html", ".xml"})
NON_VISIBLE_TAGS = frozenset({"script", "style"})
VALID_ERROR_CODES = frozenset(
    {
        "INVALID_INPUT",
        "MISSING_CORPUS",
        "CORRUPT_CORPUS",
        "UNSUPPORTED_DOCUMENT",
        "EXTRACTION_FAILURE",
        "STORAGE_FAILURE",
    }
)


@dataclass(frozen=True)
class CorpusChunk:
    """One citation-preserving local SEC text chunk.

    Attributes:
        chunk_id: Deterministic local chunk identifier.
        ordinal: Zero-based chunk order within its document.
        accession: Parent SEC filing accession.
        form: Parent SEC form type.
        filing_date: Parent filing date.
        document_name: Parent filing or exhibit name.
        source_url: Parent SEC source URL.
        relative_path: Parent case-relative source path.
        start_offset: Inclusive normalized-text offset.
        end_offset: Exclusive normalized-text offset.
        text: Non-empty normalized chunk text.
    """

    chunk_id: str
    ordinal: int
    accession: str
    form: str
    filing_date: date
    document_name: str
    source_url: str
    relative_path: str
    start_offset: int
    end_offset: int
    text: str

    def __post_init__(self) -> None:
        """Validate chunk identity, receipt fields, and normalized offsets.

        Args:
            None.

        Returns:
            None.

        Raises:
            ValueError: If chunk values are incomplete or inconsistent.
        """
        if not self.chunk_id.strip() or self.ordinal < 0 or not self.text.strip():
            raise ValueError("chunk identity or text is invalid")
        if self.start_offset < 0 or self.end_offset <= self.start_offset:
            raise ValueError("chunk offsets are invalid")
        if self.end_offset - self.start_offset != len(self.text):
            raise ValueError("chunk offsets must match text length")
        for field_name in ("accession", "form", "document_name", "source_url", "relative_path"):
            if not str(getattr(self, field_name)).strip():
                raise ValueError("chunk receipt is incomplete")

    def to_dict(self) -> dict[str, Any]:
        """Serialize a chunk into JSON-safe data.

        Args:
            None.

        Returns:
            Dictionary with an ISO filing date.
        """
        return {**self.__dict__, "filing_date": self.filing_date.isoformat()}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CorpusChunk":
        """Reconstruct and validate one serialized chunk.

        Args:
            value: JSON-safe chunk payload.

        Returns:
            Validated chunk object.
        """
        return cls(**{**value, "filing_date": date.fromisoformat(value["filing_date"])})


@dataclass(frozen=True)
class CorpusPreparationError:
    """Safe failure from local SEC corpus preparation.

    Attributes:
        code: Stable machine-readable failure class.
        message: Safe caller-facing explanation.
        retryable: Whether retrying later may succeed.
    """

    code: Literal[
        "INVALID_INPUT",
        "MISSING_CORPUS",
        "CORRUPT_CORPUS",
        "UNSUPPORTED_DOCUMENT",
        "EXTRACTION_FAILURE",
        "STORAGE_FAILURE",
    ]
    message: str
    retryable: bool

    def __post_init__(self) -> None:
        """Validate error code and safe message.

        Args:
            None.

        Returns:
            None.

        Raises:
            ValueError: If code or message is invalid.
        """
        if self.code not in VALID_ERROR_CODES or not self.message.strip():
            raise ValueError("corpus preparation error is invalid")


@dataclass(frozen=True)
class CorpusPreparationResult:
    """Completed local chunk artifact or one recoverable preparation failure.

    Attributes:
        chunks: Non-empty prepared chunks on success.
        artifact_path: Local JSONL artifact path on success.
        error: Safe error on failure.
    """

    chunks: tuple[CorpusChunk, ...] = ()
    artifact_path: Path | None = None
    error: CorpusPreparationError | None = None

    def __post_init__(self) -> None:
        """Require exactly one valid success or failure branch.

        Args:
            None.

        Returns:
            None.

        Raises:
            ValueError: If result branches are ambiguous.
        """
        success = bool(self.chunks) and self.artifact_path is not None and self.error is None
        failure = not self.chunks and self.artifact_path is None and self.error is not None
        if not (success or failure):
            raise ValueError("corpus preparation result is invalid")


class _VisibleTextParser(HTMLParser):
    """Collect visible text while omitting script and style content."""

    def __init__(self) -> None:
        """Initialize text collection and hidden-tag depth.

        Args:
            None.

        Returns:
            None.
        """
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Track entry into a non-visible tag.

        Args:
            tag: Parsed tag name.
            attrs: Parsed tag attributes, unused for text extraction.

        Returns:
            None.
        """
        del attrs
        if tag.lower() in NON_VISIBLE_TAGS:
            self.hidden_depth += 1

    def handle_endtag(self, tag: str) -> None:
        """Track exit from a non-visible tag.

        Args:
            tag: Parsed tag name.

        Returns:
            None.
        """
        if tag.lower() in NON_VISIBLE_TAGS and self.hidden_depth:
            self.hidden_depth -= 1

    def handle_data(self, data: str) -> None:
        """Append visible parsed text in encounter order.

        Args:
            data: Parsed text content.

        Returns:
            None.
        """
        if not self.hidden_depth:
            self.parts.append(data)


def _failure(
    code: Literal[
        "INVALID_INPUT",
        "MISSING_CORPUS",
        "CORRUPT_CORPUS",
        "UNSUPPORTED_DOCUMENT",
        "EXTRACTION_FAILURE",
        "STORAGE_FAILURE",
    ],
    message: str,
    retryable: bool,
) -> CorpusPreparationResult:
    """Build a safe failed corpus-preparation result.

    Args:
        code: Stable preparation failure code.
        message: Caller-safe failure explanation.
        retryable: Whether retrying later may work.

    Returns:
        Failure-only preparation result.
    """
    return CorpusPreparationResult(error=CorpusPreparationError(code, message, retryable))


def _safe_document_path(case_directory: Path, document: DownloadedDocument) -> Path:
    """Resolve one receipt path and enforce case-directory containment.

    Args:
        case_directory: Existing local investigation case directory.
        document: Valid manifest document receipt.

    Returns:
        Existing regular file path below the case directory.

    Raises:
        ValueError: If path escapes the case or is not a regular file.
    """
    root = case_directory.resolve()
    target = (root / document.relative_path).resolve()
    try:
        target.relative_to(root)
    except ValueError as error:
        raise ValueError("document path escapes case directory") from error
    if not target.is_file():
        raise ValueError("document source file is missing")
    return target


def _decode_document(body: bytes) -> str:
    """Decode SEC source bytes with deterministic lossless fallback.

    Args:
        body: Verified local SEC source bytes.

    Returns:
        Decoded source text.
    """
    if body.startswith(b"\x1f\x8b"):
        import gzip
        try:
            body = gzip.decompress(body)
        except Exception:
            pass
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError:
        return body.decode("latin-1")


def _normalized_text(document: DownloadedDocument, body: bytes) -> str:
    """Extract normalized visible text from one supported local SEC document.

    Args:
        document: Parent document receipt.
        body: Verified exact source bytes.

    Returns:
        Non-empty normalized text in document encounter order.

    Raises:
        ValueError: If type is unsupported or extraction produces no visible text.
    """
    suffix = Path(document.document_name).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError("document type is unsupported")
    decoded = _decode_document(body)
    if suffix in {".htm", ".html", ".xml"}:
        parser = _VisibleTextParser()
        parser.feed(decoded)
        parser.close()
        decoded = " ".join(parser.parts)
    text = " ".join(decoded.split())
    if not text:
        raise ValueError("document has no visible text")
    return text


def _chunk_text(text: str) -> tuple[tuple[int, int, str], ...]:
    """Split normalized text into overlapping non-empty stable chunks.

    Args:
        text: Non-empty normalized document text.

    Returns:
        Ordered `(start_offset, end_offset, text)` chunk tuple.
    """
    chunks: list[tuple[int, int, str]] = []
    start = 0
    while start < len(text):
        maximum_end = min(start + CHUNK_CHARACTER_LIMIT, len(text))
        end = maximum_end
        if maximum_end < len(text):
            boundary = text.rfind(" ", start, maximum_end)
            if boundary > start:
                end = boundary
        chunk = text[start:end]
        if chunk:
            chunks.append((start, end, chunk))
        if end == len(text):
            break
        start = end - CHUNK_OVERLAP_CHARACTERS
    return tuple(chunks)


def _chunk_id(corpus_id: str, document: DownloadedDocument, ordinal: int) -> str:
    """Create a deterministic citation-safe chunk identifier.

    Args:
        corpus_id: Parent local corpus identity.
        document: Parent SEC document receipt.
        ordinal: Zero-based document-local chunk order.

    Returns:
        Stable readable chunk identifier.
    """
    identity = f"{corpus_id}|{document.accession}|{document.document_name}|{ordinal}"
    digest = sha256(identity.encode("utf-8")).hexdigest()[:CHUNK_ID_DIGEST_LENGTH]
    return f"{document.accession}-{ordinal}-{digest}"


def _chunks_for_document(corpus: PulledCorpus, document: DownloadedDocument, body: bytes) -> tuple[CorpusChunk, ...]:
    """Build receipt-preserving chunks for one verified source document.

    Args:
        corpus: Parent case-local corpus.
        document: Source document receipt.
        body: Verified exact source bytes.

    Returns:
        Ordered chunks for the source document.
    """
    text = _normalized_text(document, body)
    return tuple(
        CorpusChunk(
            chunk_id=_chunk_id(corpus.corpus_id, document, ordinal),
            ordinal=ordinal,
            accession=document.accession,
            form=document.form,
            filing_date=document.filing_date,
            document_name=document.document_name,
            source_url=document.source_url,
            relative_path=document.relative_path,
            start_offset=start,
            end_offset=end,
            text=chunk_text,
        )
        for ordinal, (start, end, chunk_text) in enumerate(_chunk_text(text))
    )


def _artifact_paths(case_directory: Path) -> tuple[Path, Path]:
    """Return fixed local chunk artifact and preparation-manifest paths.

    Args:
        case_directory: Parent investigation case directory.

    Returns:
        `(chunks_jsonl_path, preparation_manifest_path)` tuple.
    """
    directory = case_directory / INDEX_DIRECTORY
    return directory / CHUNKS_FILENAME, directory / PREPARATION_MANIFEST_FILENAME


def _artifact_metadata(corpus: PulledCorpus, chunk_count: int) -> dict[str, Any]:
    """Build deterministic metadata used to validate artifact reuse.

    Args:
        corpus: Current local SEC corpus receipt set.
        chunk_count: Number of generated chunks.

    Returns:
        JSON-safe artifact identity payload.
    """
    return {
        "corpus_id": corpus.corpus_id,
        "document_sha256": [document.sha256 for document in corpus.documents],
        "chunk_count": chunk_count,
        "artifact": CHUNKS_FILENAME,
    }


def _load_reusable_artifact(case_directory: Path, corpus: PulledCorpus) -> CorpusPreparationResult | None:
    """Load an existing artifact only when it exactly matches current receipts.

    Args:
        case_directory: Existing local case directory.
        corpus: Current manifest-derived corpus.

    Returns:
        Successful result for a matching artifact, otherwise None.
    """
    chunks_path, manifest_path = _artifact_paths(case_directory)
    if not chunks_path.is_file() or not manifest_path.is_file():
        return None
    try:
        metadata = json.loads(manifest_path.read_text(encoding="utf-8"))
        expected = _artifact_metadata(corpus, metadata["chunk_count"])
        if metadata != expected:
            return None
        chunks = tuple(
            CorpusChunk.from_dict(json.loads(line))
            for line in chunks_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
        if len(chunks) != metadata["chunk_count"] or not chunks:
            return None
        return CorpusPreparationResult(chunks=chunks, artifact_path=chunks_path)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError):
        return None


def _atomic_write(path: Path, content: str) -> None:
    """Atomically replace one UTF-8 local artifact file.

    Args:
        path: Final artifact path below case-local index directory.
        content: Complete UTF-8 text content to persist.

    Returns:
        None.

    Raises:
        OSError: If local artifact write or replacement fails.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as temporary:
        temporary.write(content)
        temporary_path = Path(temporary.name)
    try:
        os.replace(temporary_path, path)
    except OSError:
        temporary_path.unlink(missing_ok=True)
        raise


def _write_artifact(case_directory: Path, corpus: PulledCorpus, chunks: tuple[CorpusChunk, ...]) -> Path:
    """Persist complete local chunks and their reuse metadata atomically per file.

    Args:
        case_directory: Existing local case directory.
        corpus: Current validated SEC corpus.
        chunks: Complete non-empty prepared chunks.

    Returns:
        Written JSONL artifact path.
    """
    chunks_path, manifest_path = _artifact_paths(case_directory)
    chunk_content = "".join(json.dumps(chunk.to_dict(), sort_keys=True) + "\n" for chunk in chunks)
    metadata_content = json.dumps(_artifact_metadata(corpus, len(chunks)), indent=2, sort_keys=True) + "\n"
    _atomic_write(chunks_path, chunk_content)
    _atomic_write(manifest_path, metadata_content)
    return chunks_path


def prepare_sec_corpus(case_directory: Path) -> CorpusPreparationResult:
    """Prepare verified local SEC files as citation-preserving text chunks.

    Args:
        case_directory: Existing case directory containing one SEC corpus manifest.

    Returns:
        Local chunk artifact result or a safe structured failure. This function never performs
        network I/O, provider calls, embeddings, retrieval, or LLM work.
    """
    try:
        directory = Path(case_directory)
        if not directory.is_dir():
            raise ValueError("case directory is invalid")
    except (TypeError, ValueError):
        return _failure("INVALID_INPUT", "Case directory is invalid.", False)
    try:
        corpus = read_corpus_manifest(directory)
    except StorageError:
        return _failure("MISSING_CORPUS", "Local SEC corpus manifest is unavailable.", False)
    try:
        reusable = _load_reusable_artifact(directory, corpus)
        if reusable is not None:
            return reusable
        chunks: list[CorpusChunk] = []
        for document in corpus.documents:
            source_path = _safe_document_path(directory, document)
            body = source_path.read_bytes()
            if sha256(body).hexdigest() != document.sha256:
                return _failure("CORRUPT_CORPUS", "Local SEC document receipt does not match stored content.", False)
            chunks.extend(_chunks_for_document(corpus, document, body))
        if not chunks:
            return _failure("EXTRACTION_FAILURE", "Local SEC corpus contains no indexable text.", False)
        artifact_path = _write_artifact(directory, corpus, tuple(chunks))
        return CorpusPreparationResult(chunks=tuple(chunks), artifact_path=artifact_path)
    except ValueError as error:
        if str(error) == "document type is unsupported":
            return _failure("UNSUPPORTED_DOCUMENT", "Local SEC document format is not supported.", False)
        return _failure("CORRUPT_CORPUS", "Local SEC corpus files are missing or unsafe.", False)
    except OSError:
        return _failure("STORAGE_FAILURE", "Local SEC chunk storage is unavailable.", True)
    except Exception:
        return _failure("EXTRACTION_FAILURE", "Local SEC document text could not be prepared.", False)
