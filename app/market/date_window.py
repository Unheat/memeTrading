"""Look-ahead-safe date-window filtering and Point-in-Time (PIT) clamping.

## Donor code provenance

| Local symbol | Reuse type | Exact donor location | Deliberate changes |
| --- | --- | --- | --- |
| `app.market.date_window.to_utc` | adapted | `reference/tradingagents/tradingagents/dataflows/date_window.py:19-21`, `to_utc` | retained UTC normalization semantics |
| `app.market.date_window.in_window` | adapted | `reference/tradingagents/tradingagents/dataflows/date_window.py:24-32`, `in_window` | added explicit `run_as_of_date` dual-mode support to permit undated items in live runs while blocking in historical backtest runs |
| `app.market.date_window.coverage_gap` | adapted | `reference/tradingagents/tradingagents/dataflows/date_window.py:35-60`, `coverage_gap` | retained coverage truncation warning generation |
| `app.market.date_window.as_of` | adapted | `reference/tradingagents/tradingagents/dataflows/date_window.py:69-80`, `as_of` | made `run_as_of_date` pass-through when None for unconstrained live research |
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable


def to_utc(dt: datetime) -> datetime:
    """Normalize a datetime to UTC-aware; a naive value is assumed to be UTC."""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _parse_date(date_str: str | None) -> datetime | None:
    if not date_str:
        return None
    try:
        # Support YYYY-MM-DD as well as ISO timestamps
        clean = str(date_str).strip()
        if len(clean) >= 10:
            return datetime.strptime(clean[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        pass
    return None


def as_of(requested: str | None, run_as_of_date: str | None = None) -> str | None:
    """Clamp a requested date to run_as_of_date.

    If run_as_of_date is None (normal live research mode), passes through the requested date untouched.
    In backtest mode (run_as_of_date is set), the returned date will never be later than run_as_of_date.
    """
    if not run_as_of_date:
        return requested
    if not requested:
        return run_as_of_date
    parsed_req = _parse_date(requested)
    parsed_cutoff = _parse_date(run_as_of_date)
    if parsed_req is not None and parsed_cutoff is not None and parsed_req <= parsed_cutoff:
        return requested
    return run_as_of_date


def in_window(
    pub_dt: datetime | None,
    start_dt: datetime,
    end_dt: datetime,
    run_as_of_date: str | None = None,
) -> bool:
    """Whether an item belongs in the half-open window [start, end + 1 day).

    Dual-mode:
    - Normal live research (run_as_of_date is None): undated items (pub_dt=None) are preserved.
    - Backtest mode (run_as_of_date is set to historical date): undated items are excluded to
      prevent live unanchored web content from contaminating historical evaluations.
    """
    end = to_utc(end_dt)
    start = to_utc(start_dt)
    if pub_dt is not None:
        item_dt = to_utc(pub_dt)
        return start <= item_dt < (end + timedelta(days=1))

    # pub_dt is None (undated item)
    if run_as_of_date is None:
        # Live research mode: allow undated web artifacts freely
        return True

    # Backtest mode: check if window reaches near current time
    now_utc = datetime.now(timezone.utc)
    is_live_window = end >= (now_utc - timedelta(days=1))
    return is_live_window


def coverage_gap(
    dates: Iterable[datetime | None],
    start_date: str,
    end_date: str,
    source: str,
    subject: str,
) -> str | None:
    """Placeholder for a window a feed did not fully observe, else None.

    News and social feeds often truncate to their latest 7-30 days regardless of the requested window.
    Returning empty without explanation leads LLMs to infer an absence of events.
    This helper detects when a historical window was unobserved due to vendor retention limits.
    """
    now = datetime.now(timezone.utc)
    valid_dates = [to_utc(d) for d in dates if d is not None]
    oldest = min(valid_dates, default=now)

    start_parsed = _parse_date(start_date)
    end_parsed = _parse_date(end_date)

    if end_parsed and end_parsed.date() > now.date():
        reason = "the requested window extends past today"
    elif start_parsed and oldest.date() > start_parsed.date():
        reason = f"it only serves recent items (coverage starts {oldest:%Y-%m-%d})"
    else:
        return None

    return f"<{source} unavailable for {start_date}..{end_date}: {reason}, so this is not an absence of {subject}>"
