"""Production SEC claim assessor with OpenAI-compatible endpoint and offline fallback.

Uses OpenAI-compatible endpoint (OpenAI / OpenRouter) when credentials exist;
falls back to deterministic grounded keyword assessor in keyless/offline environments.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Sequence
from app.sec.retrieval import RetrievedSecChunk

logger = logging.getLogger(__name__)

APPROVED_BASE_URLS = (
    "https://api.openai.com/v1",
    "https://openrouter.ai/api/v1",
)


def get_default_sec_assessor():
    """Return an Assessor callable for verify_sec_claim."""
    api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY")
    base_url = "https://openrouter.ai/api/v1" if os.environ.get("OPENROUTER_API_KEY") else "https://api.openai.com/v1"
    model = os.environ.get("SEC_ASSESSOR_MODEL", "gpt-4o-mini" if "openai.com" in base_url else "openai/gpt-4o-mini")

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
                approved_base_urls=APPROVED_BASE_URLS,
            )
            return create_openai_compatible_sec_assessor(config)
        except Exception as exc:
            logger.warning("Failed to initialize remote OpenAI-compatible assessor: %s; using deterministic fallback", exc)

    # Deterministic fallback for offline / keyless testing
    def _deterministic_assessor(claim: str, chunks: Sequence[RetrievedSecChunk]) -> dict[str, Any]:
        if not chunks:
            return {
                "verdict": "INSUFFICIENT_EVIDENCE",
                "confidence": 0.20,
                "explanation": "No local filing excerpts were retrieved for this claim.",
                "evidence_for_chunk_ids": [],
                "evidence_against_chunk_ids": [],
                "material_sec_facts": {},
                "missing_evidence": ["Relevant SEC 8-K, 10-K, or 10-Q filing documents."],
                "suggested_document_types": ["8-K", "10-Q"],
            }

        claim_lower = claim.lower()
        claim_terms = set(re.findall(r"\b\w{4,}\b", claim_lower))

        for_ids: list[str] = []
        against_ids: list[str] = []

        contradiction_markers = ["non-binding", "subject to", "letter of intent", "loi", "terminated", "no agreement", "declined"]

        for item in chunks:
            text_lower = item.chunk.text.lower()
            matching_terms = sum(1 for t in claim_terms if t in text_lower)
            if matching_terms >= 2:
                # Check for explicit contradictions
                if any(m in text_lower for m in contradiction_markers) and any(kw in claim_lower for kw in ["binding", "definitive", "signed deal", "acquired"]):
                    against_ids.append(item.chunk.chunk_id)
                else:
                    for_ids.append(item.chunk.chunk_id)

        if against_ids:
            return {
                "verdict": "CONTRADICTED",
                "confidence": 0.85,
                "explanation": f"Filing excerpt explicitly contradicts claim: {claim}.",
                "evidence_for_chunk_ids": [],
                "evidence_against_chunk_ids": against_ids[:2],
                "material_sec_facts": {"contradiction_detected": True},
                "missing_evidence": [],
                "suggested_document_types": [],
            }
        elif for_ids:
            return {
                "verdict": "CONFIRMED",
                "confidence": 0.80,
                "explanation": f"Filing evidence supports claim: {claim}.",
                "evidence_for_chunk_ids": for_ids[:2],
                "evidence_against_chunk_ids": [],
                "material_sec_facts": {"support_detected": True},
                "missing_evidence": [],
                "suggested_document_types": [],
            }
        else:
            first_chunk_id = chunks[0].chunk.chunk_id if chunks else ""
            return {
                "verdict": "INSUFFICIENT_EVIDENCE",
                "confidence": 0.35,
                "explanation": "Retrieved excerpts do not conclusively confirm or contradict the claim.",
                "evidence_for_chunk_ids": [],
                "evidence_against_chunk_ids": [],
                "material_sec_facts": {},
                "missing_evidence": ["Direct contractual confirmation in primary agreement exhibit."],
                "suggested_document_types": ["EX-10.1", "8-K"],
            }

    return _deterministic_assessor
