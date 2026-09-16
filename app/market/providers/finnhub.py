"""Finnhub keyed provider: analyst consensus and structured insider transactions.

Black-box dependency: Finnhub REST API v1 (free tier 60 req/min). No donor code.
Env key: FINNHUB_API_KEY. Unconfigured client is silently disabled (empty results).
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request
from typing import Any

from app.market.schemas import MarketDataError

logger = logging.getLogger(__name__)

API_KEY_ENV = "FINNHUB_API_KEY"
BASE_URL = "https://finnhub.io/api/v1"
DEFAULT_TIMEOUT_SECONDS = 10


class FinnhubClient:
    """Client for Finnhub analyst consensus and insider transaction endpoints."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.getenv(API_KEY_ENV, "").strip() or None

    @property
    def is_configured(self) -> bool:
        """True when an API key is available."""
        return bool(self.api_key)

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Fetch one Finnhub endpoint; raises MarketDataError on failure."""
        if not self.is_configured:
            return None
        safe_params = dict(params or {})
        safe_params["token"] = self.api_key
        query = urllib.parse.urlencode(safe_params)
        url = f"{BASE_URL}{path}?{query}"
        headers = {
            "Accept": "application/json",
            "X-Finnhub-Token": str(self.api_key),
            "User-Agent": "MemeTradingResearchAgent/0.1",
        }
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
                body = response.read().decode("utf-8")
                return json.loads(body)
        except Exception as exc:
            import re
            sanitized = re.sub(r"token=[^&\s]+", "token=REDACTED", str(exc))
            raise MarketDataError("finnhub", f"{path} request failed: {sanitized}") from None

    def get_recommendation_trends(self, ticker: str) -> list[dict[str, Any]]:
        """Return consensus recommendation trends (newest first)."""
        if not self.is_configured:
            return []
        try:
            raw = self._get("/stock/recommendation", {"symbol": ticker})
        except MarketDataError:
            raise
        except Exception as exc:
            raise MarketDataError("finnhub", f"recommendation trends failed: {exc}") from exc
        return raw if isinstance(raw, list) else []

    def get_price_target(self, ticker: str) -> dict[str, Any] | None:
        """Return analyst price-target dict or None when unavailable."""
        if not self.is_configured:
            return None
        try:
            raw = self._get("/stock/price-target", {"symbol": ticker})
        except MarketDataError:
            raise
        except Exception as exc:
            raise MarketDataError("finnhub", f"price target failed: {exc}") from exc
        return raw if isinstance(raw, dict) and raw else None

    def get_insider_transactions(self, ticker: str, limit: int = 20) -> list[dict[str, Any]]:
        """Return pre-parsed insider (Form 4) transaction rows, newest first.

        Rows carry SEC transaction codes as-is (S/P/F/M/G); interpretation of
        codes stays with the caller/LLM, matching the fullplan Form 4 policy.
        """
        if not self.is_configured:
            return []
        try:
            raw = self._get("/stock/insider-transactions", {"symbol": ticker})
        except MarketDataError:
            raise
        except Exception as exc:
            raise MarketDataError("finnhub", f"insider transactions failed: {exc}") from exc
        if not isinstance(raw, dict):
            return []
        rows: list[dict[str, Any]] = []
        for item in (raw.get("data") or [])[:limit]:
            if not isinstance(item, dict):
                continue
            rows.append(
                {
                    "name": item.get("name"),
                    "transaction_code": item.get("transactionCode"),
                    "shares": item.get("share"),
                    "price": item.get("transactionPrice"),
                    "change": item.get("change"),
                    "filed_at": item.get("filedAt"),
                    "web_url": item.get("webUrl"),
                }
            )
        return rows
