"""Standardized compliant SEC User-Agent identity initialization."""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

DEFAULT_SEC_IDENTITY = "MemeTradingResearchAgent research@memetrading.internal"


def ensure_sec_identity(custom_identity: str | None = None) -> str:
    """Ensure compliant SEC User-Agent identity is configured.

    Sets both SEC_USER_AGENT and EDGAR_IDENTITY environment variables,
    and calls edgar.set_identity if edgartools is installed.
    """
    ident = (
        custom_identity
        or os.environ.get("SEC_EDGAR_USER_AGENT")
        or os.environ.get("SEC_USER_AGENT")
        or os.environ.get("EDGAR_IDENTITY")
        or DEFAULT_SEC_IDENTITY
    ).strip()

    os.environ["SEC_EDGAR_USER_AGENT"] = ident
    os.environ["SEC_USER_AGENT"] = ident
    os.environ["EDGAR_IDENTITY"] = ident

    try:
        from edgar import set_identity
        set_identity(ident)
    except Exception as exc:
        logger.debug("edgar.set_identity call skipped or unavailable: %s", exc)

    return ident
