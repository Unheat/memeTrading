"""Pydantic pre-validation coercion helpers for model-generated numeric fields.

## Donor code provenance

| Local symbol | Reuse type | Exact donor location | Deliberate changes |
| --- | --- | --- | --- |
| `app.contracts.coercion.coerce_optional_float` | adapted | `reference/tradingagents/tradingagents/agents/schemas.py:33-60`, `_coerce_optional_float` | made public helper for Pydantic validators; handles currency symbols, percentage drops, and placeholder strings |
"""

from __future__ import annotations

from typing import Any

_NULLISH_FLOAT = {"", "none", "n/a", "na", "null", "nil", "-", "tbd", "unknown", "nan"}


def coerce_optional_float(value: Any) -> float | None:
    """Normalize an LLM-written optional numeric field before Pydantic validation.

    Handles:
    - String placeholders like "None", "N/A", "TBD", "-" -> None
    - Percentage strings like "15%" where a raw price level was requested -> None
    - Currency formatted numbers like "$1,234.50" or "€120.00" -> 1234.50
    - Existing float / int values -> float
    - Non-numeric strings or ranges ("150-160") -> None
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None

    text = value.strip()
    if text.lower() in _NULLISH_FLOAT or text.endswith("%"):
        return None

    cleaned = text.replace(",", "").lstrip("$€£¥").strip()
    try:
        val = float(cleaned)
        import math
        if math.isnan(val) or math.isinf(val):
            return None
        return val
    except ValueError:
        return None
