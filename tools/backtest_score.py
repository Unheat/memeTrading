#!/usr/bin/env python3
"""Backtest scorer: grade historical investigation decisions against forward returns.

Batch D of the audit fix plan (AUDIT_FIX_PLAN.md). Code fixes make the model correct;
this harness is the honest measurement loop that makes profitability claims empirical.

For every persisted case it extracts the committee's decision (verdict, reward-to-risk
ratio, upside anchor, bear floor, entry price, decision date), fetches forward prices
from an injectable provider, and reports per-horizon calibration: hit rate, average
forward return, realized vs predicted upside, and whether the 3:1-class hurdle and the
0.60 win-probability assumption earn their keep.

Usage:
    python tools/backtest_score.py --cases-root cases --horizons 63,126,252
    python tools/backtest_score.py --cases-root cases --json-out backtest.json
"""
from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Default forward-return horizons in trading days (~3/6/12 months).
DEFAULT_HORIZONS = (63, 126, 252)
# Calendar-day conversion for fetching forward prices from daily bars.
CALENDAR_DAYS_PER_TRADING_DAY = 1.4

# Verdict prefixes that committed (or would have committed) capital.
_APPROVED_PREFIX = "APPROVED_LONG"
_PAPER_PREFIX = "PAPER_TRADE_WATCH"

PriceProvider = Callable[[str, datetime, datetime], float | None]


def _parse_decision_date(raw: Any) -> datetime | None:
    """Parse a case's decision timestamp into an aware UTC datetime.

    Args:
        raw: created_at value from investigation.json.

    Returns:
        Datetime or None when unparseable.
    """
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def load_case_records(cases_root: Path | str) -> list[dict[str, Any]]:
    """Extract decision records from every persisted case.

    Args:
        cases_root: Directory containing per-case subdirectories.

    Returns:
        List of decision records with identity, verdict, anchors, and entry price.
    """
    records: list[dict[str, Any]] = []
    root = Path(cases_root)
    if not root.exists():
        return records
    for case_dir in sorted(root.iterdir()):
        investigation = case_dir / "investigation.json"
        if not investigation.exists():
            continue
        try:
            data = json.loads(investigation.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Skipping unreadable case %s: %s", case_dir.name, exc)
            continue
        verdict_obj = data.get("ic_verdict") or {}
        market = data.get("market_context") or {}
        price = (market.get("quote") or {}).get("price")
        decision_date = _parse_decision_date(data.get("created_at"))
        if not price or not decision_date:
            logger.warning("Skipping case %s: missing price or decision date", case_dir.name)
            continue
        records.append({
            "case_id": str(data.get("case_id") or case_dir.name),
            "ticker": str(data.get("ticker") or "").upper(),
            "decision_date": decision_date,
            "entry_price": float(price),
            "verdict": str(verdict_obj.get("verdict") or "UNKNOWN"),
            "reward_to_risk_ratio": verdict_obj.get("reward_to_risk_ratio"),
            "upside_anchor": verdict_obj.get("upside_anchor"),
            "bear_floor": verdict_obj.get("bear_floor"),
            "allocation_pct": verdict_obj.get("kelly_position_size_pct", 0.0),
            "paper_trade": bool(verdict_obj.get("paper_trade")),
        })
    return records


def yfinance_price_provider(ticker: str, start: datetime, end: datetime) -> float | None:
    """Fetch a closing price from yfinance; returns None on any failure.

    Args:
        ticker: Stock symbol.
        start: Window start (inclusive).
        end: Window end (inclusive).

    Returns:
        Last available close in the window, or None.
    """
    try:
        import yfinance as yf

        history = yf.Ticker(ticker).history(
            start=start.strftime("%Y-%m-%d"), end=(end + timedelta(days=1)).strftime("%Y-%m-%d")
        )
        if history is None or history.empty:
            return None
        return float(history["Close"].iloc[-1])
    except Exception as exc:
        logger.warning("Price fetch failed for %s: %s", ticker, exc)
        return None


def forward_returns(
    record: dict[str, Any],
    price_provider: PriceProvider,
    horizons: tuple[int, ...],
) -> dict[int, float | None]:
    """Compute forward total returns for one decision record.

    Args:
        record: Decision record from load_case_records.
        price_provider: Injectable price source.
        horizons: Trading-day horizons to evaluate.

    Returns:
        Mapping of horizon (trading days) to fractional return, or None per horizon.
    """
    returns: dict[int, float | None] = {}
    for horizon in horizons:
        end = record["decision_date"] + timedelta(days=int(horizon * CALENDAR_DAYS_PER_TRADING_DAY))
        if end > datetime.now(timezone.utc):
            returns[horizon] = None
            continue
        future_price = price_provider(record["ticker"], record["decision_date"], end)
        returns[horizon] = (
            (future_price - record["entry_price"]) / record["entry_price"]
            if future_price and record["entry_price"] > 0
            else None
        )
    return returns


def _bucket_stats(bucket: list[dict[str, Any]], horizon: int) -> dict[str, Any]:
    """Summarize one verdict bucket at one horizon.

    Args:
        bucket: Decision records with a "returns" mapping attached.
        horizon: Trading-day horizon to summarize.

    Returns:
        Count, hit rate, mean forward return, mean predicted upside, calibration error.
    """
    realized = [r["returns"].get(horizon) for r in bucket]
    realized = [r for r in realized if r is not None]
    predicted = [
        (r.get("upside_anchor") - r["entry_price"]) / r["entry_price"]
        for r in bucket
        if r.get("upside_anchor") and r["entry_price"] > 0
    ]
    predicted = [p for p in predicted if p is not None]
    return {
        "count": len(bucket),
        "scored": len(realized),
        "hit_rate": round(sum(1 for r in realized if r > 0) / len(realized), 4) if realized else None,
        "avg_forward_return": round(statistics.fmean(realized), 4) if realized else None,
        "avg_predicted_upside": round(statistics.fmean(predicted), 4) if predicted else None,
        "calibration_error": (
            round(statistics.fmean(predicted) - statistics.fmean(realized), 4)
            if predicted and realized
            else None
        ),
    }


def score_cases(
    records: list[dict[str, Any]],
    price_provider: PriceProvider,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
) -> dict[str, Any]:
    """Grade all decision records against forward returns.

    Args:
        records: Decision records from load_case_records.
        price_provider: Injectable price source.
        horizons: Trading-day horizons to evaluate.

    Returns:
        Report dict with per-bucket, per-horizon calibration statistics.
    """
    for record in records:
        record["returns"] = forward_returns(record, price_provider, horizons)

    buckets = {
        "approved": [r for r in records if r["verdict"].startswith(_APPROVED_PREFIX)],
        "paper_trade": [r for r in records if r["verdict"].startswith(_PAPER_PREFIX) or r["paper_trade"]],
        "no_position": [
            r for r in records
            if not r["verdict"].startswith(_APPROVED_PREFIX) and not r["verdict"].startswith(_PAPER_PREFIX)
        ],
    }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "horizons_trading_days": list(horizons),
        "total_cases": len(records),
        "buckets": {
            name: {f"h{horizon}": _bucket_stats(bucket, horizon) for horizon in horizons}
            for name, bucket in buckets.items()
        },
    }


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for the backtest scorer.

    Args:
        argv: Optional CLI argument override.

    Returns:
        Process exit code.
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S")
    parser = argparse.ArgumentParser(description="Score investigation decisions against forward returns")
    parser.add_argument("--cases-root", default="cases", help="Directory containing case subdirectories")
    parser.add_argument("--horizons", default=",".join(str(h) for h in DEFAULT_HORIZONS), help="Comma-separated trading-day horizons")
    parser.add_argument("--json-out", default=None, help="Optional path to write the JSON report")
    args = parser.parse_args(argv)

    horizons = tuple(int(h) for h in str(args.horizons).split(",") if h.strip())
    records = load_case_records(args.cases_root)
    if not records:
        print("No scoreable cases found.")
        return 1
    report = score_cases(records, yfinance_price_provider, horizons)
    rendered = json.dumps(report, indent=2, default=str)
    print(rendered)
    if args.json_out:
        Path(args.json_out).write_text(rendered, encoding="utf-8")
        print(f"\nReport written to {args.json_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
