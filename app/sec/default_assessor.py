"""Production SEC claim assessor with an OpenAI-compatible structured-output boundary.

Uses the configured hosted model when credentials exist. When the provider is unavailable,
the fallback fails closed with an insufficient-evidence assessment; deterministic code never
infers claim support from natural-language keywords.
"""
from __future__ import annotations

import logging
import os
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from app.sec.retrieval import RetrievedSecChunk
from app.sec.verifier import AssessorUnavailableError

logger = logging.getLogger(__name__)


def _gateway_model_name(model: str) -> str:
    """Remove the LiteLLM OpenAI transport prefix for direct SDK gateway calls.

    Args:
        model: Model identifier from ordered LiteLLM endpoint configuration.

    Returns:
        Gateway-native model identifier suitable for the OpenAI-compatible SDK.
    """
    return model.removeprefix("openai/")


def _insufficient_evidence_assessment(_: str, __: Sequence[RetrievedSecChunk]) -> dict[str, Any]:
    """Return a conservative result when no structured SEC assessment is available.

    Args:
        _: Claim intentionally not interpreted by deterministic code.
        __: Retrieved chunks intentionally not interpreted by deterministic code.

    Returns:
        Schema-valid insufficient-evidence assessment with no asserted citations.
    """
    return {
        "verdict": "INSUFFICIENT_EVIDENCE",
        "confidence": 0.0,
        "explanation": "No approved structured SEC assessment is available for this claim.",
        "evidence_for_chunk_ids": [],
        "evidence_against_chunk_ids": [],
        "material_sec_facts": {},
        "missing_evidence": ["A structured assessment of the retrieved primary filing excerpts."],
        "suggested_document_types": [],
    }


def _fallback_on_unavailable(
    assessor: Callable[[str, Sequence[RetrievedSecChunk]], Mapping[str, Any]],
) -> Callable[[str, Sequence[RetrievedSecChunk]], Mapping[str, Any]]:
    """Wrap a hosted assessor so provider outages fail closed without language heuristics.

    Args:
        assessor: Structured remote assessor callable.

    Returns:
        Callable that returns insufficient evidence if the provider is unavailable.
    """
    def assess(claim: str, chunks: Sequence[RetrievedSecChunk]) -> Mapping[str, Any]:
        """Assess one claim or fail closed if the provider cannot respond.

        Args:
            claim: SEC claim to assess.
            chunks: Retrieved local SEC excerpts.

        Returns:
            Hosted structured assessment or conservative insufficient-evidence result.
        """
        try:
            return assessor(claim, chunks)
        except AssessorUnavailableError:
            logger.warning("SEC assessor unavailable; returning insufficient evidence without deterministic language inference")
            return _insufficient_evidence_assessment(claim, chunks)

    return assess


def get_default_sec_assessor() -> Callable[[str, Sequence[RetrievedSecChunk]], Mapping[str, Any]]:
    """Return a structured SEC assessor or conservative offline fallback.

    Returns:
        Callable satisfying the SEC verifier assessment contract.
    """
    from app.config import load_config

    try:
        cfg = load_config()
        primary_endpoint = cfg.llm.models[0]
        configured_base_url = primary_endpoint.base_url
        configured_model = primary_endpoint.model
        api_key = primary_endpoint.resolve_api_key()
    except Exception:
        configured_base_url = None
        configured_model = "openai/gpt-4o-mini"
        api_key = os.environ.get("OPENAI_API_KEY")

    base_url = (configured_base_url or "https://api.openai.com/v1").strip().rstrip("/")
    model = _gateway_model_name(configured_model)

    if api_key:
        try:
            from app.sec.openai_compatible_assessor import (
                OpenAICompatibleAssessorConfig,
                create_openai_compatible_sec_assessor,
            )

            config = OpenAICompatibleAssessorConfig(
                base_url=base_url,
                api_key=api_key.strip(),
                model=model,
            )
            return _fallback_on_unavailable(create_openai_compatible_sec_assessor(config))
        except Exception as exc:
            logger.warning("Failed to initialize remote OpenAI-compatible assessor: %s; returning insufficient evidence", exc)

    return _insufficient_evidence_assessment
