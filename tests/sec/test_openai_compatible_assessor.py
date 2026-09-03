"""Tests for the bounded OpenAI-compatible SEC assessor adapter."""

from __future__ import annotations

from datetime import date
import json
from types import SimpleNamespace

import pytest

from app.sec.corpus import CorpusChunk
from app.sec.retrieval import RetrievedSecChunk


BASE_URL = "https://provider.example/v1"
MODEL = "provider/model"
API_KEY = "test-key"


class FakeCompletions:
    """Record one structured completion request and return configurable content."""

    def __init__(self, content: str | None = None, error: Exception | None = None) -> None:
        """Initialize the fake completion endpoint.

        Args:
            content: JSON content returned by the fake model.
            error: Optional exception raised instead of a response.

        Returns:
            None.
        """
        self.content = content
        self.error = error
        self.requests: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        """Record a request and return one OpenAI-shaped completion.

        Args:
            **kwargs: Completion request arguments.

        Returns:
            Minimal completion response object.

        Raises:
            Exception: Configured provider failure.
        """
        self.requests.append(kwargs)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(
            choices=(SimpleNamespace(message=SimpleNamespace(content=self.content)),),
        )


class FakeClient:
    """Expose the minimum OpenAI-compatible chat-completions surface."""

    def __init__(self, completions: FakeCompletions) -> None:
        """Initialize a fake chat client.

        Args:
            completions: Completion endpoint double.

        Returns:
            None.
        """
        self.chat = SimpleNamespace(completions=completions)


def _chunk(chunk_id: str, text: str) -> RetrievedSecChunk:
    """Build one minimal retrieved SEC chunk for assessor tests.

    Args:
        chunk_id: Stable local candidate ID.
        text: Local SEC text supplied to the assessor.

    Returns:
        Retrieved chunk with receipt fields.
    """
    chunk = CorpusChunk(
        chunk_id=chunk_id,
        ordinal=0,
        accession="0000000000-26-000001",
        form="10-Q",
        filing_date=date(2026, 9, 3),
        document_name="report.htm",
        source_url="https://www.sec.gov/Archives/report.htm",
        relative_path="filings/report.htm",
        start_offset=0,
        end_offset=len(text),
        text=text,
    )
    return RetrievedSecChunk(chunk, 1, 1, 0.1, None, "NOT_APPLIED")


def _assessment(chunk_id: str) -> dict[str, object]:
    """Return the mapping expected by the existing verifier.

    Args:
        chunk_id: Retrieved chunk selected as supporting evidence.

    Returns:
        Valid assessor mapping.
    """
    return {
        "verdict": "CONFIRMED",
        "confidence": 0.8,
        "explanation": "The presented filing chunk supports the claim.",
        "evidence_for_chunk_ids": [chunk_id],
        "evidence_against_chunk_ids": [],
        "material_sec_facts": {"revenue_change": "25 percent"},
        "missing_evidence": [],
        "suggested_document_types": [],
    }


def _config(base_url: str = BASE_URL):
    """Create an approved hosted-provider configuration.

    Args:
        base_url: Provider endpoint to validate.

    Returns:
        Assessor configuration under test.
    """
    from app.sec.openai_compatible_assessor import OpenAICompatibleAssessorConfig

    return OpenAICompatibleAssessorConfig(
        base_url=base_url,
        api_key=API_KEY,
        model=MODEL,
        approved_base_urls=(BASE_URL,),
    )


@pytest.mark.parametrize(
    "base_url",
    ("http://provider.example/v1", "https://unapproved.example/v1", "https://key@provider.example/v1?debug=yes"),
)
def test_config_rejects_unapproved_or_unsafe_provider_url(base_url: str) -> None:
    """Reject provider URLs outside the deployment allowlist.

    Args:
        base_url: Unsafe or unapproved endpoint candidate.

    Returns:
        None. Assertion verifies boundary validation.
    """
    with pytest.raises(ValueError):
        _config(base_url)


def test_assessor_sends_bounded_structured_request_without_tools() -> None:
    """Send only claim and local chunk text in a strict schema request.

    Returns:
        None. Assertions verify prompt and API boundary.
    """
    from app.sec.openai_compatible_assessor import create_openai_compatible_sec_assessor

    completions = FakeCompletions(json.dumps(_assessment("chunk-1")))
    assessor = create_openai_compatible_sec_assessor(_config(), FakeClient(completions))

    result = assessor("Revenue increased by 25 percent.", (_chunk("chunk-1", "Revenue increased by 25 percent."),))

    assert result == _assessment("chunk-1")
    request = completions.requests[0]
    assert request["model"] == MODEL
    assert "tools" not in request
    assert request["response_format"]["json_schema"]["strict"] is True
    prompt = request["messages"][1]["content"]
    assert "chunk-1" in prompt
    assert "Revenue increased by 25 percent." in prompt
    assert "https://www.sec.gov" not in prompt
    assert "filings/report.htm" not in prompt


def test_assessor_maps_provider_failure_to_safe_availability_error() -> None:
    """Hide raw provider failures behind the injected-assessor error contract.

    Returns:
        None. Assertion verifies safe retryable failure type.
    """
    from app.sec.openai_compatible_assessor import AssessorUnavailableError, create_openai_compatible_sec_assessor

    assessor = create_openai_compatible_sec_assessor(_config(), FakeClient(FakeCompletions(error=RuntimeError("provider detail"))))

    with pytest.raises(AssessorUnavailableError):
        assessor("Revenue increased.", (_chunk("chunk-1", "Revenue increased."),))


def test_assessor_rejects_malformed_model_content() -> None:
    """Reject non-object model content before it reaches the verifier.

    Returns:
        None. Assertion verifies parser boundary.
    """
    from app.sec.openai_compatible_assessor import create_openai_compatible_sec_assessor

    assessor = create_openai_compatible_sec_assessor(_config(), FakeClient(FakeCompletions("not-json")))

    with pytest.raises(ValueError):
        assessor("Revenue increased.", (_chunk("chunk-1", "Revenue increased."),))
