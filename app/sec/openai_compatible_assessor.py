"""Bounded OpenAI-compatible assessor for case-local SEC evidence."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import json
from typing import Any
from urllib.parse import urlsplit

from app.sec.retrieval import RetrievedSecChunk
from app.sec.verifier import AssessorUnavailableError


DEFAULT_REQUEST_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_OUTPUT_TOKENS = 1_200
MAX_PROMPT_CHARACTERS = 30_000
MAX_CHUNK_TEXT_CHARACTERS = 4_000
DETERMINISTIC_TEMPERATURE = 0
RESPONSE_SCHEMA_NAME = "sec_assessment"
VALID_VERDICTS = (
    "CONFIRMED",
    "PARTIALLY_CONFIRMED",
    "CONTRADICTED",
    "INSUFFICIENT_EVIDENCE",
)
ASSESSMENT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "verdict",
        "confidence",
        "explanation",
        "evidence_for_chunk_ids",
        "evidence_against_chunk_ids",
        "material_sec_facts",
        "missing_evidence",
        "suggested_document_types",
    ],
    "properties": {
        "verdict": {"type": "string", "enum": list(VALID_VERDICTS)},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "explanation": {"type": "string"},
        "evidence_for_chunk_ids": {"type": "array", "items": {"type": "string"}},
        "evidence_against_chunk_ids": {"type": "array", "items": {"type": "string"}},
        "material_sec_facts": {"type": "object"},
        "missing_evidence": {"type": "array", "items": {"type": "string"}},
        "suggested_document_types": {"type": "array", "items": {"type": "string"}},
    },
}
SYSTEM_INSTRUCTION = (
    "Assess only the supplied SEC claim and local retrieved chunks. "
    "Use only presented chunk IDs as evidence. Return the requested JSON object."
)


def _normalized_url(value: str) -> str:
    """Validate and normalize one approved provider base URL.

    Args:
        value: Candidate provider endpoint.

    Returns:
        Canonical endpoint without a trailing slash.

    Raises:
        ValueError: If the endpoint is not a safe HTTPS or local HTTP base URL.
    """
    normalized = value.strip().rstrip("/")
    parsed = urlsplit(normalized)
    is_local = parsed.hostname in {"localhost", "127.0.0.1"}
    valid_scheme = parsed.scheme == "https" or (is_local and parsed.scheme == "http")
    if (
        not normalized
        or not valid_scheme
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("provider base URL is invalid")
    return normalized


@dataclass(frozen=True)
class OpenAICompatibleAssessorConfig:
    """Validated configuration for one approved hosted model provider.

    Attributes:
        base_url: Explicit OpenAI-compatible HTTP/HTTPS endpoint.
        api_key: Deployment-supplied provider credential.
        model: Provider model identifier with structured-output support.
        approved_base_urls: Optional deployment allowlist of permitted endpoints.
        timeout_seconds: Bounded provider request timeout.
        max_output_tokens: Bounded model response size.
    """

    base_url: str
    api_key: str
    model: str
    approved_base_urls: tuple[str, ...] = ()
    timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS

    def __post_init__(self) -> None:
        """Validate provider identity, credential presence, and named limits.

        Args:
            None.

        Returns:
            None.

        Raises:
            ValueError: If configuration is incomplete or unsafe.
        """
        base_url = _normalized_url(self.base_url)
        allowed = tuple(_normalized_url(item) for item in self.approved_base_urls) if self.approved_base_urls else ()
        if not self.api_key.strip() or not self.model.strip():
            raise ValueError("provider configuration is invalid")
        if allowed and base_url not in allowed:
            raise ValueError("provider base URL not in approved allowlist")
        if self.timeout_seconds <= 0 or self.max_output_tokens <= 0:
            raise ValueError("provider limits are invalid")
        object.__setattr__(self, "base_url", base_url)
        object.__setattr__(self, "approved_base_urls", allowed)


def _prompt(claim: str, chunks: Sequence[RetrievedSecChunk]) -> str:
    """Build a bounded prompt from only a claim and retrieved local chunks.

    Args:
        claim: Narrow SEC claim to assess.
        chunks: Candidate chunks selected by case-local retrieval.

    Returns:
        Prompt containing only approved evidence fields.

    Raises:
        ValueError: If the bounded prompt cannot contain any chunk.
    """
    parts = [f"Claim:\n{claim.strip()}\n\nRetrieved chunks:"]
    used_characters = len("\n".join(parts))
    for item in chunks:
        text = item.chunk.text[:MAX_CHUNK_TEXT_CHARACTERS]
        chunk_part = f"\n\nchunk_id: {item.chunk.chunk_id}\ntext:\n{text}"
        if used_characters + len(chunk_part) > MAX_PROMPT_CHARACTERS:
            break
        parts.append(chunk_part)
        used_characters += len(chunk_part)
    if len(parts) == 1:
        raise ValueError("no retrieved chunk fits within the prompt limit")
    return "\n".join(parts)


def _response_content(response: Any) -> str:
    """Extract one non-empty text content value from a chat completion.

    Args:
        response: OpenAI-compatible Chat Completions response object.

    Returns:
        Non-empty JSON text.

    Raises:
        ValueError: If the response has no usable message content.
    """
    try:
        content = response.choices[0].message.content
    except (AttributeError, IndexError, KeyError, TypeError) as error:
        raise ValueError("model response is invalid") from error
    if not isinstance(content, str) or not content.strip():
        raise ValueError("model response is invalid")
    return content


def _client_from_config(config: OpenAICompatibleAssessorConfig) -> Any:
    """Create one black-box OpenAI SDK client without making a request.

    Args:
        config: Validated hosted-provider configuration.

    Returns:
        Configured OpenAI-compatible client.

    Raises:
        AssessorUnavailableError: If the optional SDK cannot be initialized.
    """
    try:
        from openai import OpenAI

        return OpenAI(api_key=config.api_key, base_url=config.base_url, timeout=config.timeout_seconds)
    except Exception as error:
        raise AssessorUnavailableError() from error


def create_openai_compatible_sec_assessor(
    config: OpenAICompatibleAssessorConfig,
    client: Any | None = None,
) -> Callable[[str, Sequence[RetrievedSecChunk]], Mapping[str, Any]]:
    """Create an injected structured assessor for the existing SEC verifier.

    Args:
        config: Validated approved-provider configuration.
        client: Optional OpenAI-compatible client double for tests.

    Returns:
        Callable returning the verifier's proposed assessment mapping.
    """
    resolved_client = client if client is not None else _client_from_config(config)

    def assess(claim: str, chunks: Sequence[RetrievedSecChunk]) -> Mapping[str, Any]:
        """Request one strict structured assessment for retrieved SEC evidence.

        Args:
            claim: Narrow SEC claim to assess.
            chunks: Case-local retrieval candidates only.

        Returns:
            Parsed proposed assessment mapping.

        Raises:
            AssessorUnavailableError: If the approved provider cannot respond.
            ValueError: If the model response is malformed.
        """
        prompt = _prompt(claim, chunks)
        try:
            response = resolved_client.chat.completions.create(
                model=config.model,
                messages=(
                    {"role": "system", "content": SYSTEM_INSTRUCTION},
                    {"role": "user", "content": prompt},
                ),
                temperature=DETERMINISTIC_TEMPERATURE,
                max_tokens=config.max_output_tokens,
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": RESPONSE_SCHEMA_NAME, "strict": True, "schema": ASSESSMENT_SCHEMA},
                },
            )
        except Exception as error:
            raise AssessorUnavailableError() from error
        parsed = json.loads(_response_content(response))
        if not isinstance(parsed, Mapping):
            raise ValueError("model response is not an object")
        return dict(parsed)

    return assess
