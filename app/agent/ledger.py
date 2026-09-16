"""Append-only durable records for bounded deep-research execution.

Work-item concepts are adapted from GPT Researcher's deep-research planning contract
at reference/gpt-researcher/gpt_researcher/skills/deep_research.py:259-378. The
local ledger, source provenance, and budget semantics are locally written.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Literal, Mapping

EVENTS_FILENAME = "research-ledger.jsonl"
VALID_WORK_STATUSES = frozenset({"queued", "admitted", "completed", "blocked", "dropped"})


@dataclass(frozen=True)
class ResearchWorkItem:
    """One bounded, model-proposed research question.

    Args:
        work_id: Stable work-item identifier.
        question: Narrow answerable research question.
        evidence_tier: Required source quality tier.
        priority: Larger values run first.
        depth: Breadth/depth queue level.
        candidate_id: Optional isolated candidate owner.
        parent_work_id: Optional parent reflection item.
        status: Lifecycle state.
        dependencies: Work IDs that must complete first.

    Returns:
        JSON-safe queue record.
    """

    work_id: str
    question: str
    evidence_tier: str
    priority: int
    depth: int
    candidate_id: str | None = None
    parent_work_id: str | None = None
    status: Literal["queued", "admitted", "completed", "blocked", "dropped"] = "queued"
    dependencies: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Validate the durable work-item contract."""
        if not self.work_id.strip() or not self.question.strip() or not self.evidence_tier.strip():
            raise ValueError("work item identity is invalid")
        if self.status not in VALID_WORK_STATUSES or self.depth < 0:
            raise ValueError("work item lifecycle is invalid")

    def to_dict(self) -> dict[str, Any]:
        """Serialize this work item for ledger storage."""
        return {**asdict(self), "dependencies": list(self.dependencies)}


@dataclass(frozen=True)
class SourceDocument:
    """Immutable retrieved source identity and content provenance."""

    source_id: str
    canonical_url: str
    source_tier: str
    retrieved_at: str
    content_sha256: str
    content_type: str
    candidate_id: str | None = None
    title: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the source document for durable storage."""
        return asdict(self)


@dataclass(frozen=True)
class SourceExcerpt:
    """Durable source-local citation excerpt."""

    excerpt_id: str
    source_id: str
    text: str
    locator: str
    candidate_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the excerpt for durable storage."""
        return asdict(self)


@dataclass(frozen=True)
class ClaimRecord:
    """Auditable factual claim linked to durable source excerpts."""

    claim_id: str
    statement: str
    claim_type: str
    status: Literal["supported", "unsupported", "contradicted", "inconclusive"]
    subject_id: str | None = None
    as_of: str | None = None
    evidence_link_ids: tuple[str, ...] = field(default_factory=tuple)
    limitations: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the claim record for durable storage."""
        return {
            **asdict(self),
            "evidence_link_ids": list(self.evidence_link_ids),
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True)
class EvidenceLink:
    """Explicit relationship between an excerpt and a claim."""

    evidence_link_id: str
    claim_id: str
    excerpt_id: str
    relation: Literal["supports", "contradicts", "context"] = "supports"

    def to_dict(self) -> dict[str, Any]:
        """Serialize the link for durable storage."""
        return asdict(self)


def canonical_input_digest(tool_name: str, arguments: Mapping[str, Any]) -> str:
    """Return a stable idempotency key for one tool execution.

    Args:
        tool_name: Model-visible tool name.
        arguments: JSON-compatible normalized arguments.

    Returns:
        SHA-256 digest for cache and ledger identity.
    """
    payload = json.dumps({"tool": tool_name, "arguments": arguments}, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(payload.encode("utf-8")).hexdigest()


def append_ledger_event(case_directory: Path | str, event_type: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Append one atomic JSON event before derived state is materialized.

    Args:
        case_directory: Existing durable case directory.
        event_type: Stable event category.
        payload: JSON-compatible event details.

    Returns:
        Written event payload including UTC timestamp.

    Raises:
        ValueError: If the case directory or event type is invalid.
    """
    directory = Path(case_directory)
    if not directory.is_dir() or not event_type.strip():
        raise ValueError("ledger event destination is invalid")
    event = {"event_type": event_type, "recorded_at": datetime.now(timezone.utc).isoformat(), "payload": dict(payload)}
    with (directory / EVENTS_FILENAME).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True, default=str) + "\n")
    return event


def read_ledger_events(case_directory: Path | str) -> list[dict[str, Any]]:
    """Read valid append-only ledger events in write order.

    Args:
        case_directory: Existing case directory.

    Returns:
        Ordered event payloads, or an empty list when no ledger exists.
    """
    path = Path(case_directory) / EVENTS_FILENAME
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
