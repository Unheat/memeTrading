"""Outer backtest and historical evaluation harness.

Evaluates decision quality, valuation accuracy, and forensic risk detection across historical
dates and tickers without modifying the core research pipeline.

## Donor code provenance

| Local symbol | Reuse type | Exact donor location | Deliberate changes |
| --- | --- | --- | --- |
| `app.evaluation.backtest.generate_date_grid` | adapted | `reference/tradingagents/tradingagents/backtest.py:32-60`, `iter_grid` | retained grid iteration and date validation; added clean error handling |
| `app.evaluation.backtest.settle_decision` | adapted | `reference/tradingagents/tradingagents/backtest.py:63-100`, `_alpha` and `_DIRECTION` | integrated with local yfinance provider to compute realized forward returns and benchmark alpha |
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.agent.runner import run_investigation
from app.agent.state import BudgetLimits, ResearchRequest
from app.market.provider import fetch_history

logger = logging.getLogger(__name__)


def _parse_canonical_date(date_str: str) -> datetime:
    """Parse a date string in YYYY-MM-DD format."""
    clean = str(date_str).strip()
    try:
        parsed = datetime.strptime(clean[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"date must be in YYYY-MM-DD format, got {date_str!r}") from exc
    return parsed


def generate_date_grid(start_date: str, end_date: str, every_n_days: int = 30) -> list[str]:
    """Generate chronological analysis dates from start_date to end_date, never past today.

    :param start_date: Starting date in YYYY-MM-DD.
    :param end_date: Ending date in YYYY-MM-DD.
    :param every_n_days: Step size in days (minimum 1).
    :returns: List of ISO date strings.
    """
    if every_n_days < 1:
        raise ValueError("every_n_days must be at least 1")

    start = _parse_canonical_date(start_date)
    end = _parse_canonical_date(end_date)
    if end < start:
        raise ValueError(f"end_date {end_date} cannot be before start_date {start_date}")

    now = datetime.now(timezone.utc)
    last_allowed = min(end, now)

    dates: list[str] = []
    cursor = start
    while cursor <= last_allowed:
        dates.append(cursor.strftime("%Y-%m-%d"))
        cursor += timedelta(days=every_n_days)

    return dates


@dataclass
class BacktestDecisionRecord:
    """Captured decision metrics from one historical investigation run."""

    ticker: str
    as_of_date: str
    case_id: str
    status: str
    verdict: str | None = None
    conviction_tier: str | None = None
    kelly_position_size_pct: float | None = None
    asymmetry_ratio: float | None = None
    current_price: float | None = None
    fair_value: float | None = None
    bear_floor: float | None = None
    forensic_verdict: str | None = None
    artifacts: list[str] = field(default_factory=list)


def run_backtest_cell(
    ticker: str,
    as_of_date: str,
    cases_root: Path | str = "cases/backtests",
    model: Any | None = None,
    budget_max_tool_calls: int = 25,
) -> BacktestDecisionRecord:
    """Execute one self-contained historical investigation cell.

    Uses the existing atomic pipeline with explicit as_of_date clamping.
    """
    clean_ticker = ticker.strip().upper()
    req = ResearchRequest(
        query=f"Conduct full institutional equity diligence on {clean_ticker} as of {as_of_date}.",
        ticker=clean_ticker,
        as_of_date=as_of_date,
        depth="standard",
        requested_position_decision=True,
        budget=BudgetLimits(max_total_tool_calls=budget_max_tool_calls, max_identical_calls=2),
    )

    res = run_investigation(
        request=req,
        cases_root=cases_root,
        model=model,
        generate_media=False,
    )

    verdict_str = None
    conviction_str = None
    kelly_pct = None
    asym = None
    curr_px = None
    fv = None
    bf = None
    forensic_v = None

    if res.manifest:
        # Read from investigation.json if available
        inv_path = Path(res.case_directory) / "investigation.json"
        if inv_path.exists():
            try:
                import json
                inv_data = json.loads(inv_path.read_text(encoding="utf-8"))
                ic = inv_data.get("ic_verdict") or {}
                if isinstance(ic, dict):
                    verdict_str = ic.get("verdict")
                    conviction_str = ic.get("conviction_tier")
                    kelly_pct = ic.get("kelly_position_size_pct")
                    asym = ic.get("reward_to_risk_ratio")
                    curr_px = ic.get("current_price")
                    fv = ic.get("base_target_price")
                    bf = ic.get("bear_floor_price")
                forensic = inv_data.get("forensic_report") or {}
                if isinstance(forensic, dict):
                    forensic_v = forensic.get("verdict")
            except Exception as exc:
                logger.warning("Failed to parse investigation.json for backtest record: %s", exc)

    return BacktestDecisionRecord(
        ticker=clean_ticker,
        as_of_date=as_of_date,
        case_id=res.case_id,
        status=res.status,
        verdict=verdict_str,
        conviction_tier=conviction_str,
        kelly_position_size_pct=kelly_pct,
        asymmetry_ratio=asym,
        current_price=curr_px,
        fair_value=fv,
        bear_floor=bf,
        forensic_verdict=forensic_v,
        artifacts=list(res.artifacts.keys()),
    )


def settle_decision(
    ticker: str,
    as_of_date: str,
    forward_days: int = 90,
    benchmark_ticker: str = "SPY",
) -> dict[str, Any]:
    """Calculate forward realized return and benchmark alpha after forward_days.

    :param ticker: Target equity symbol.
    :param as_of_date: Original decision date (YYYY-MM-DD).
    :param forward_days: Forward evaluation window in calendar days (e.g. 30, 60, 90).
    :param benchmark_ticker: Benchmark for alpha calculation (default SPY).
    :returns: Dictionary with start_price, forward_price, realized_return, alpha.
    """
    decision_dt = _parse_canonical_date(as_of_date)
    settle_dt = decision_dt + timedelta(days=forward_days)
    settle_str = settle_dt.strftime("%Y-%m-%d")

    now = datetime.now(timezone.utc)
    if settle_dt > now:
        return {
            "status": "pending_settlement",
            "settlement_date": settle_str,
            "message": f"Settlement date {settle_str} is in the future.",
        }

    try:
        # Fetch asset history up to settlement date
        hist_asset = fetch_history(ticker, period="2y", as_of_date=settle_str)
        hist_bench = fetch_history(benchmark_ticker, period="2y", as_of_date=settle_str)

        dates_a = [d[:10] for d in hist_asset["dates"]]
        closes_a = hist_asset["close"]
        dates_b = [d[:10] for d in hist_bench["dates"]]
        closes_b = hist_bench["close"]

        # Find closest bar on or after as_of_date
        idx_start_a = next((i for i, d in enumerate(dates_a) if d >= as_of_date[:10]), None)
        idx_end_a = len(closes_a) - 1

        idx_start_b = next((i for i, d in enumerate(dates_b) if d >= as_of_date[:10]), None)
        idx_end_b = len(closes_b) - 1

        if idx_start_a is None or idx_start_b is None or idx_end_a <= idx_start_a:
            return {"status": "insufficient_bars", "ticker": ticker, "settle_date": settle_str}

        p_start_a = closes_a[idx_start_a]
        p_end_a = closes_a[idx_end_a]
        ret_a = (p_end_a - p_start_a) / p_start_a if p_start_a > 0 else 0.0

        p_start_b = closes_b[idx_start_b]
        p_end_b = closes_b[idx_end_b]
        ret_b = (p_end_b - p_start_b) / p_start_b if p_start_b > 0 else 0.0

        alpha = ret_a - ret_b

        return {
            "status": "settled",
            "ticker": ticker.upper(),
            "as_of_date": as_of_date[:10],
            "settle_date": settle_str,
            "start_price": round(p_start_a, 2),
            "end_price": round(p_end_a, 2),
            "asset_return_pct": round(ret_a * 100, 2),
            "benchmark_return_pct": round(ret_b * 100, 2),
            "alpha_pct": round(alpha * 100, 2),
        }
    except Exception as exc:
        return {"status": "error", "message": f"Settlement calculation failed: {exc}"}
