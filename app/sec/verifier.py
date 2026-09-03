"""Constrained local-only verification of claims against one SEC corpus."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from app.sec.retrieval import RetrievedSecChunk, search_sec_corpus
from app.sec.schemas import SECVerification, SecEvidence


MAX_CLAIM_CHARACTERS = 2_000
MAX_EVIDENCE_CITATIONS = 5
MAX_EXPLANATION_CHARACTERS = 4_000
MAX_MISSING_EVIDENCE = 5
MAX_SUGGESTED_DOCUMENT_TYPES = 5
VALID_ERROR_CODES = frozenset(
    {
        "INVALID_INPUT",
        "RETRIEVAL_FAILED",
        "ASSESSOR_UNAVAILABLE",
        "INVALID_ASSESSMENT",
        "INTERNAL_FAILURE",
    }
)


@dataclass(frozen=True)
class VerificationError:
    """Safe failure returned by the local SEC verifier.

    Attributes:
        code: Stable machine-readable failure class.
        message: Safe caller-facing failure explanation.
        retryable: Whether a later retry might succeed.
    """

    code: Literal[
        "INVALID_INPUT",
        "RETRIEVAL_FAILED",
        "ASSESSOR_UNAVAILABLE",
        "INVALID_ASSESSMENT",
        "INTERNAL_FAILURE",
    ]
    message: str
    retryable: bool

    def __post_init__(self) -> None:
        """Validate stable safe failure fields.

        Args: None.

        Returns: None.

        Raises:
            ValueError: If code or message is invalid.
        """
        if self.code not in VALID_ERROR_CODES or not self.message.strip():
            raise ValueError("verification error is invalid")


@dataclass(frozen=True)
class VerificationResult:
    """One successful SEC verification or one safe failure."""

    verification: SECVerification | None = None
    error: VerificationError | None = None

    def __post_init__(self) -> None:
        """Require exactly one result branch.

        Args: None.

        Returns: None.

        Raises:
            ValueError: If success and error branches are ambiguous.
        """
        if (self.verification is None) == (self.error is None):
            raise ValueError("verification result is invalid")


Assessor = Callable[[str, Sequence[RetrievedSecChunk]], Mapping[str, Any]]


def _failure(code: VerificationError.code, message: str, retryable: bool) -> VerificationError:
    """Create one validated safe verifier failure.

    Args:
        code: Stable failure category.
        message: Safe caller-facing message.
        retryable: Retry indicator.

    Returns:
        Validated verifier error.
    """
    return VerificationError(code, message, retryable)


def _string_list(value: Any, field_name: str, maximum: int, *, unique: bool = False) -> tuple[str, ...]:
    """Validate a bounded assessor-provided string list.

    Args:
        value: Candidate list from the assessor response.
        field_name: Field name for validation failures.
        maximum: Maximum allowed entries.
        unique: Whether duplicate values are prohibited.

    Returns:
        Validated trimmed immutable text tuple.

    Raises:
        ValueError: If the assessor response field is malformed.
    """
    if isinstance(value, str) or not isinstance(value, Sequence) or len(value) > maximum:
        raise ValueError(f"{field_name} is invalid")
    normalized = tuple(item.strip() for item in value if isinstance(item, str) and item.strip())
    if len(normalized) != len(value) or (unique and len(set(normalized)) != len(normalized)):
        raise ValueError(f"{field_name} is invalid")
    return normalized


def _evidence_from_ids(candidate_by_id: Mapping[str, RetrievedSecChunk], chunk_ids: tuple[str, ...]) -> tuple[SecEvidence, ...]:
    """Convert assessor-selected local chunk IDs into immutable SEC evidence.

    Args:
        candidate_by_id: Retrieved candidate chunks keyed by local identity.
        chunk_ids: Validated assessor-selected candidate identities.

    Returns:
        SEC evidence records built solely from local chunk receipts.

    Raises:
        ValueError: If any ID was not retrieved for this claim.
    """
    evidence: list[SecEvidence] = []
    for chunk_id in chunk_ids:
        candidate = candidate_by_id.get(chunk_id)
        if candidate is None:
            raise ValueError("assessment cites an unknown local chunk")
        chunk = candidate.chunk
        evidence.append(
            SecEvidence(
                accession=chunk.accession,
                form=chunk.form,
                filing_date=chunk.filing_date,
                document=chunk.document_name,
                quote=chunk.text,
                source_url=chunk.source_url,
            )
        )
    return tuple(evidence)


def _verification_from_assessment(
    claim: str,
    candidates: Sequence[RetrievedSecChunk],
    assessment: Mapping[str, Any],
) -> SECVerification:
    """Validate a local assessment and construct a grounded verification result.

    Args:
        claim: Original narrow SEC claim.
        candidates: Retrieval-bounded local evidence candidates.
        assessment: Assessor's structured proposed outcome.

    Returns:
        Validated SEC verification with receipt-owned evidence.

    Raises:
        ValueError: If assessor output is malformed or cites non-candidates.
    """
    required_fields = {
        "verdict",
        "confidence",
        "explanation",
        "evidence_for_chunk_ids",
        "evidence_against_chunk_ids",
        "material_sec_facts",
        "missing_evidence",
        "suggested_document_types",
    }
    if not isinstance(assessment, Mapping) or not required_fields.issubset(assessment):
        raise ValueError("assessment is incomplete")
    explanation = assessment["explanation"]
    confidence = assessment["confidence"]
    material_facts = assessment["material_sec_facts"]
    if (
        not isinstance(assessment["verdict"], str)
        or not isinstance(explanation, str)
        or not explanation.strip()
        or len(explanation) > MAX_EXPLANATION_CHARACTERS
        or isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or not isinstance(material_facts, Mapping)
    ):
        raise ValueError("assessment is invalid")
    evidence_for_ids = _string_list(assessment["evidence_for_chunk_ids"], "evidence_for_chunk_ids", MAX_EVIDENCE_CITATIONS, unique=True)
    evidence_against_ids = _string_list(assessment["evidence_against_chunk_ids"], "evidence_against_chunk_ids", MAX_EVIDENCE_CITATIONS, unique=True)
    if set(evidence_for_ids) & set(evidence_against_ids):
        raise ValueError("assessment reuses a citation across verdict sides")
    missing_evidence = _string_list(assessment["missing_evidence"], "missing_evidence", MAX_MISSING_EVIDENCE, unique=True)
    suggested_document_types = _string_list(assessment["suggested_document_types"], "suggested_document_types", MAX_SUGGESTED_DOCUMENT_TYPES, unique=True)
    candidate_by_id = {item.chunk.chunk_id: item for item in candidates}
    return SECVerification(
        claim=claim,
        verdict=assessment["verdict"],
        confidence=float(confidence),
        explanation=explanation,
        evidence_for=_evidence_from_ids(candidate_by_id, evidence_for_ids),
        evidence_against=_evidence_from_ids(candidate_by_id, evidence_against_ids),
        material_sec_facts=dict(material_facts),
        missing_evidence=missing_evidence,
        suggested_document_types=suggested_document_types,
    )


def verify_sec_claim(
    case_directory: Path,
    claim: str,
    embed_query: Callable[[str], Sequence[float]],
    assessor: Assessor | None,
    reranker: Callable[[str, Sequence[Any]], Sequence[tuple[str, float]]] | None = None,
) -> VerificationResult:
    """Assess one claim using only a case-local SEC corpus and local assessor.

    Args:
        case_directory: Existing prepared and indexed local case directory.
        claim: Narrow claim for SEC-only verification.
        embed_query: Injected local query embedding callable.
        assessor: Injected local-only structured claim assessor.
        reranker: Optional injected local retrieval reranker.

    Returns:
        Grounded SEC verification or a safe structured error.
    """
    if not isinstance(claim, str) or not claim.strip() or len(claim) > MAX_CLAIM_CHARACTERS:
        return VerificationResult(error=_failure("INVALID_INPUT", "SEC verification claim is invalid.", False))
    if assessor is None:
        return VerificationResult(error=_failure("ASSESSOR_UNAVAILABLE", "No approved local SEC assessor is configured.", True))
    retrieval = search_sec_corpus(Path(case_directory), claim, embed_query, reranker)
    if retrieval.error is not None:
        return VerificationResult(error=_failure("RETRIEVAL_FAILED", "Local SEC evidence retrieval is unavailable.", retrieval.error.retryable))
    try:
        assessment = assessor(claim, retrieval.results)
        verification = _verification_from_assessment(claim, retrieval.results, assessment)
        return VerificationResult(verification=verification)
    except (KeyError, TypeError, ValueError):
        return VerificationResult(error=_failure("INVALID_ASSESSMENT", "Local SEC assessment did not satisfy the evidence contract.", False))
    except Exception:
        return VerificationResult(error=_failure("INTERNAL_FAILURE", "Local SEC verification could not complete.", False))
