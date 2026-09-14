"""FRED macro provider (Federal Reserve Economic Data).

Black-box dependency: FRED REST API (free tier 120 req/min). No donor code.
Env key: FRED_API_KEY. Used only when a research question needs macro context;
not registered as an agent tool in Phase B.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

API_KEY_ENV = "FRED_API_KEY"
BASE_URL = "https://api.stlouisfed.org/fred/series/observations"
DEFAULT_TIMEOUT_SECONDS = 10


def _fred_get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    """Seam over FRED observations endpoint so tests can patch it."""
    query = "&".join(f"{k}={v}" for k, v in params.items())
    req = urllib.request.Request(f"{BASE_URL}?{query}", headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


def get_macro_series(series_id: str, limit: int = 30) -> list[dict[str, Any]]:
    """Fetch recent observations for one FRED series.

    :param series_id: FRED series identifier (e.g. "DGS10").
    :param limit: Maximum observations requested (most recent first upstream).
    :returns: Oldest->newest list of {"date", "value"} with missing ('.') values
              skipped; empty list when FRED_API_KEY is not configured.
    """
    api_key = os.getenv(API_KEY_ENV, "").strip()
    if not api_key or not series_id or not series_id.strip():
        return []

    params = {
        "series_id": series_id.strip(),
        "api_key": api_key,
        "file_type": "json",
        "sort_order": "desc",
        "limit": str(max(1, int(limit))),
    }
    try:
        raw = _fred_get(BASE_URL, params)
    except Exception as exc:
        logger.warning("FRED series %s failed: %s", series_id, exc)
        return []

    observations: list[dict[str, Any]] = []
    for entry in raw.get("observations") or []:
        raw_value = str(entry.get("value", "")).strip()
        date = entry.get("date")
        if not date or raw_value == ".":
            continue
        try:
            value = float(raw_value)
        except ValueError:
            continue
        observations.append({"date": str(date), "value": value})
    observations.reverse()  # oldest -> newest
    return observations


def get_macro_context(series_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Build a macro-context snapshot for multiple FRED series.

    :param series_ids: Non-empty list of FRED series identifiers.
    :returns: Per-series dict {"latest_value", "latest_date", "observations",
              "provider", "as_of", "status"}; failed/empty series carry
              status="unavailable" and never raise to the caller.
    """
    if not series_ids:
        raise ValueError("series_ids must be a non-empty list")

    as_of = datetime.now(timezone.utc).isoformat()
    context: dict[str, dict[str, Any]] = {}
    for series_id in series_ids:
        observations = get_macro_series(series_id)
        if observations:
            context[series_id] = {
                "latest_value": observations[-1]["value"],
                "latest_date": observations[-1]["date"],
                "observations": observations,
                "provider": "fred",
                "as_of": as_of,
                "status": "ok",
            }
        else:
            context[series_id] = {
                "latest_value": None,
                "latest_date": None,
                "observations": [],
                "provider": "fred",
                "as_of": as_of,
                "status": "unavailable",
            }
    return context
