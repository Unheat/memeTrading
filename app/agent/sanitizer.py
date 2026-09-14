"""Lightweight prompt injection sanitizer for untrusted external content.

Zero external dependencies. Filters common instruction override patterns in
scraped social posts, article text, and web search snippets.
"""
from __future__ import annotations

import re
from typing import Any

INJECTION_PATTERNS = re.compile(
    r"(ignore\s+(all\s+)?previous\s+instructions?|"
    r"you\s+are\s+now\s+(in\s+)?developer\s+mode|"
    r"system\s+override|"
    r"disregard\s+(all\s+)?prior\s+(instructions?|rules?)|"
    r"reveal\s+(your\s+)?system\s+prompt)",
    re.IGNORECASE,
)


def sanitize_untrusted_text(text: str) -> str:
    """Neutralize prompt injection attempts in raw untrusted text strings.

    Args:
        text: Raw scraped text from social media, articles, or web search.

    Returns:
        Cleaned string with instruction override patterns replaced.
    """
    if not text or not isinstance(text, str):
        return text if text is not None else ""
    return INJECTION_PATTERNS.sub("[FILTERED_INSTRUCTION]", text)


def sanitize_payload(obj: Any) -> Any:
    """Recursively sanitize string fields inside a dictionary or list payload.

    Args:
        obj: Data structure containing potentially untrusted strings.

    Returns:
        Copy of data structure with all string values sanitized.
    """
    if isinstance(obj, str):
        return sanitize_untrusted_text(obj)
    if isinstance(obj, dict):
        return {k: sanitize_payload(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_payload(item) for item in obj]
    return obj
