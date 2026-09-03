"""Validated local data contracts for SEC filing acquisition and verification."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import PurePath
import re
from typing import Any, ClassVar, Mapping
from urllib.parse import urlparse


SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
VALID_VERDICTS = frozenset(
    {"CONFIRMED", "PARTIALLY_CONFIRMED", "CONTRADICTED", "INSUFFICIENT_EVIDENCE"}
)


def _non_empty(value: str, field_name: str) -> str:
    """Validate non-blank text.

    Args:
        value: Text value to validate.
        field_name: Contract field name for errors.

    Returns:
        Trimmed text.

    Raises:
        ValueError: If the text is blank.
    """
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _http_url(value: str, field_name: str) -> str:
    """Validate a public HTTP(S) source URL.

    Args:
        value: Candidate URL.
        field_name: Contract field name for errors.

    Returns:
        Trimmed valid URL.

    Raises:
        ValueError: If the URL lacks an HTTP(S) scheme or host.
    """
    normalized = _non_empty(value, field_name)
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{field_name} must be an HTTP(S) URL")
    return normalized


def _safe_relative_path(value: str) -> str:
    """Validate a path stored relative to one case directory.

    Args:
        value: Candidate local document path.

    Returns:
        Normalized relative path text.

    Raises:
        ValueError: If the path is blank, absolute, or traverses upward.
    """
    normalized = _non_empty(value, "relative_path")
    path = PurePath(normalized)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("relative_path must stay beneath the case directory")
    return path.as_posix()


@dataclass(frozen=True)
class FilingMetadata:
    """Metadata-only record for a filing discovered from SEC data.

    Attributes:
        ticker: Normalized stock symbol.
        cik: SEC CIK digits without formatting zeroes.
        form: SEC form type.
        filing_date: Filing date.
        accession: SEC accession number.
        filing_url: Canonical SEC source URL.
        primary_document: Optional primary document name.
        exhibits: Available exhibit names.
    """

    ticker: str
    cik: str
    form: str
    filing_date: date
    accession: str
    filing_url: str
    primary_document: str | None = None
    exhibits: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Normalize and validate filing receipt values.

        Raises:
            ValueError: If receipt values or source URL are invalid.
        """
        object.__setattr__(self, "ticker", _non_empty(self.ticker, "ticker").upper())
        cik = _non_empty(self.cik, "cik")
        if not cik.isdigit():
            raise ValueError("cik must contain digits only")
        object.__setattr__(self, "cik", str(int(cik)))
        object.__setattr__(self, "form", _non_empty(self.form, "form"))
        object.__setattr__(self, "accession", _non_empty(self.accession, "accession"))
        object.__setattr__(self, "filing_url", _http_url(self.filing_url, "filing_url"))
        if self.primary_document is not None:
            object.__setattr__(self, "primary_document", _non_empty(self.primary_document, "primary_document"))
        object.__setattr__(self, "exhibits", tuple(_non_empty(item, "exhibit") for item in self.exhibits))

    def to_dict(self) -> dict[str, Any]:
        """Serialize the filing metadata into JSON-safe data.

        Returns:
            Dictionary with ISO date and list-based exhibits.
        """
        return {**self.__dict__, "filing_date": self.filing_date.isoformat(), "exhibits": list(self.exhibits)}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "FilingMetadata":
        """Reconstruct validated filing metadata from JSON-safe data.

        Args:
            value: Serialized filing metadata.

        Returns:
            Validated filing metadata.
        """
        return cls(**{**value, "filing_date": date.fromisoformat(value["filing_date"]), "exhibits": tuple(value.get("exhibits", ()))})


@dataclass(frozen=True)
class DownloadedDocument:
    """One locally stored SEC filing or exhibit with source provenance."""

    accession: str
    form: str
    filing_date: date
    document_name: str
    source_url: str
    relative_path: str
    sha256: str

    def __post_init__(self) -> None:
        """Validate immutable local-document provenance.

        Raises:
            ValueError: If receipt, URL, path, or digest values are invalid.
        """
        for field_name in ("accession", "form", "document_name"):
            object.__setattr__(self, field_name, _non_empty(getattr(self, field_name), field_name))
        object.__setattr__(self, "source_url", _http_url(self.source_url, "source_url"))
        object.__setattr__(self, "relative_path", _safe_relative_path(self.relative_path))
        if not SHA256_PATTERN.fullmatch(self.sha256):
            raise ValueError("sha256 must be a lowercase 64-character hexadecimal digest")

    def to_dict(self) -> dict[str, Any]:
        """Serialize document metadata into JSON-safe data.

        Returns:
            Dictionary with ISO filing date.
        """
        return {**self.__dict__, "filing_date": self.filing_date.isoformat()}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "DownloadedDocument":
        """Reconstruct validated document metadata from JSON-safe data.

        Args:
            value: Serialized document metadata.

        Returns:
            Validated downloaded document.
        """
        return cls(**{**value, "filing_date": date.fromisoformat(value["filing_date"])})


@dataclass(frozen=True)
class PulledCorpus:
    """One case-local set of downloaded SEC documents."""

    corpus_id: str
    ticker: str
    cik: str
    created_at: datetime
    documents: tuple[DownloadedDocument, ...]

    def __post_init__(self) -> None:
        """Validate corpus identity and document uniqueness.

        Raises:
            ValueError: If corpus values are invalid or duplicate documents exist.
        """
        object.__setattr__(self, "corpus_id", _non_empty(self.corpus_id, "corpus_id"))
        object.__setattr__(self, "ticker", _non_empty(self.ticker, "ticker").upper())
        cik = _non_empty(self.cik, "cik")
        if not cik.isdigit():
            raise ValueError("cik must contain digits only")
        object.__setattr__(self, "cik", str(int(cik)))
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must include a timezone")
        if not self.documents:
            raise ValueError("documents must not be empty")
        identities = {(document.accession, document.document_name) for document in self.documents}
        if len(identities) != len(self.documents):
            raise ValueError("documents must not repeat accession and document_name")

    @property
    def accessions(self) -> tuple[str, ...]:
        """Return accessions in first-seen order.

        Returns:
            Unique accession tuple derived from documents.
        """
        return tuple(dict.fromkeys(document.accession for document in self.documents))

    def to_dict(self) -> dict[str, Any]:
        """Serialize corpus and nested documents into JSON-safe data.

        Returns:
            Dictionary with ISO timestamp and document dictionaries.
        """
        return {**self.__dict__, "created_at": self.created_at.isoformat(), "documents": [document.to_dict() for document in self.documents]}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "PulledCorpus":
        """Reconstruct a validated corpus from JSON-safe data.

        Args:
            value: Serialized corpus data.

        Returns:
            Validated corpus.
        """
        return cls(**{**value, "created_at": datetime.fromisoformat(value["created_at"]), "documents": tuple(DownloadedDocument.from_dict(item) for item in value["documents"])})


@dataclass(frozen=True)
class SecEvidence:
    """Cited SEC passage used in one verification result."""

    accession: str
    form: str
    filing_date: date
    document: str
    quote: str
    source_url: str

    def __post_init__(self) -> None:
        """Validate required filing receipt and quotation fields.

        Raises:
            ValueError: If required citation fields are blank or URL is invalid.
        """
        for field_name in ("accession", "form", "document", "quote"):
            object.__setattr__(self, field_name, _non_empty(getattr(self, field_name), field_name))
        object.__setattr__(self, "source_url", _http_url(self.source_url, "source_url"))

    def to_dict(self) -> dict[str, Any]:
        """Serialize evidence into JSON-safe data.

        Returns:
            Dictionary with ISO filing date.
        """
        return {**self.__dict__, "filing_date": self.filing_date.isoformat()}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SecEvidence":
        """Reconstruct validated evidence from JSON-safe data.

        Args:
            value: Serialized evidence.

        Returns:
            Validated SEC evidence.
        """
        return cls(**{**value, "filing_date": date.fromisoformat(value["filing_date"])})


@dataclass(frozen=True)
class SECVerification:
    """Grounded response from a future local-only SEC verifier."""

    claim: str
    verdict: str
    confidence: float
    explanation: str
    evidence_for: tuple[SecEvidence, ...] = ()
    evidence_against: tuple[SecEvidence, ...] = ()
    material_sec_facts: Mapping[str, Any] = field(default_factory=dict)
    missing_evidence: tuple[str, ...] = ()
    suggested_document_types: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Validate verdict vocabulary and evidence requirements.

        Raises:
            ValueError: If verdict, confidence, explanation, or evidence invariants fail.
        """
        object.__setattr__(self, "claim", _non_empty(self.claim, "claim"))
        if self.verdict not in VALID_VERDICTS:
            raise ValueError("verdict is invalid")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")
        object.__setattr__(self, "explanation", _non_empty(self.explanation, "explanation"))
        object.__setattr__(self, "missing_evidence", tuple(_non_empty(item, "missing_evidence") for item in self.missing_evidence))
        object.__setattr__(self, "suggested_document_types", tuple(_non_empty(item, "suggested_document_types") for item in self.suggested_document_types))
        if self.verdict in {"CONFIRMED", "PARTIALLY_CONFIRMED"} and not self.evidence_for:
            raise ValueError("evidence_for is required for confirmed verdicts")
        if self.verdict == "CONTRADICTED" and not self.evidence_against:
            raise ValueError("evidence_against is required for contradicted verdicts")
        if self.verdict == "INSUFFICIENT_EVIDENCE" and not self.missing_evidence:
            raise ValueError("missing_evidence is required for insufficient evidence")

    def to_dict(self) -> dict[str, Any]:
        """Serialize a verifier response into JSON-safe data.

        Returns:
            Dictionary with nested evidence records converted to dictionaries.
        """
        return {
            **self.__dict__,
            "evidence_for": [item.to_dict() for item in self.evidence_for],
            "evidence_against": [item.to_dict() for item in self.evidence_against],
            "missing_evidence": list(self.missing_evidence),
            "suggested_document_types": list(self.suggested_document_types),
            "material_sec_facts": dict(self.material_sec_facts),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SECVerification":
        """Reconstruct a validated verifier response from JSON-safe data.

        Args:
            value: Serialized verification result.

        Returns:
            Validated verifier response.
        """
        return cls(
            **{
                **value,
                "evidence_for": tuple(SecEvidence.from_dict(item) for item in value.get("evidence_for", ())),
                "evidence_against": tuple(SecEvidence.from_dict(item) for item in value.get("evidence_against", ())),
                "missing_evidence": tuple(value.get("missing_evidence", ())),
                "suggested_document_types": tuple(value.get("suggested_document_types", ())),
            }
        )
