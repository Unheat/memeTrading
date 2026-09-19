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
    fs = res.final_state or {}
    case_dir = Path(cases_root) / res.case_id
    artifacts_list: list[str] = []
    inv_data: dict[str, Any] = {}
    inv_path = case_dir / "investigation.json"
    if inv_path.exists():
        artifacts_list.append("investigation.json")
        try:
            import json
            inv_data = json.loads(inv_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to parse investigation.json for backtest record: %s", exc)

    if (case_dir / "memo.md").exists():
        artifacts_list.append("memo.md")
    if (case_dir / "run-manifest.json").exists():
        artifacts_list.append("run-manifest.json")

    def _get_field(obj: Any, field_name: str) -> Any:
        if obj is None:
            return None
        if isinstance(obj, dict):
            return obj.get(field_name)
        return getattr(obj, field_name, None)

    ic = fs.get("ic_verdict") or inv_data.get("ic_verdict")
    verdict_str = _get_field(ic, "verdict")
    conviction_str = _get_field(ic, "conviction_tier")
    kelly_pct = _get_field(ic, "kelly_position_size_pct")
    asym = _get_field(ic, "reward_to_risk_ratio")

    candidates = fs.get("candidates") or inv_data.get("candidates") or {}
    curr_px = None
    fv = None
    bf = None
    forensic_v = _get_field(fs.get("forensic_report") or inv_data.get("forensic_report"), "verdict")

    for cand in candidates.values():
        if isinstance(cand, dict) and cand.get("diligence_dossier"):
            dossier = cand["diligence_dossier"]
            if bf is None:
                bf = dossier.get("bear_floor")
            if fv is None:
                val = dossier.get("valuation") or {}
                fv = val.get("fair_value") or (val.get("fair_value_range") or {}).get("base")
            if curr_px is None:
                curr_px = (dossier.get("market_context") or {}).get("quote", {}).get("price")
            if forensic_v is None:
                forensic_v = dossier.get("forensic_verdict")

    if (case_dir / "memo.md").exists():
        artifacts_list.append("memo.md")
    if (case_dir / "run-manifest.json").exists():
        artifacts_list.append("run-manifest.json")

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
        artifacts=artifacts_list,
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
        hist_asset = fetch_history(ticker, period="5y", as_of_date=settle_str)
        hist_bench = fetch_history(benchmark_ticker, period="5y", as_of_date=settle_str)

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


@dataclass
class BacktestSummary:
    """Multi-dimensional performance scorecard of the model and deterministic gates."""

    total_runs: int
    approved_longs: int
    passed_discipline: int
    validation_watch: int
    settled_runs: int
    pending_settlement: int
    hit_rate_approved_longs: float | None = None
    mean_alpha_approved_longs: float = 0.0
    mean_alpha_passed_discipline: float = 0.0
    bear_floor_breach_count: int = 0
    forensic_high_risk_count: int = 0
    forensic_high_risk_mean_return: float = 0.0
    forward_days: int = 90
    benchmark_ticker: str = "SPY"

    def render(self) -> str:
        """Render a clean terminal/markdown scorecard of backtest results."""
        lines = [
            "=" * 72,
            " 📊 INSTITUTIONAL DEEP RESEARCH BACKTEST SCORECARD",
            "=" * 72,
            f"• Forward Horizon:     {self.forward_days} days vs {self.benchmark_ticker}",
            f"• Total Evaluations:   {self.total_runs} (Settled: {self.settled_runs}, Pending: {self.pending_settlement})",
            "",
            "## 1. Investment Committee Verdict Distribution",
            f"  - Approved Longs:     {self.approved_longs}",
            f"  - Passed Discipline:  {self.passed_discipline}",
            f"  - Validation Watch:   {self.validation_watch}",
            "",
            "## 2. Decision Performance & Alpha vs Benchmark",
        ]
        if self.hit_rate_approved_longs is not None:
            lines.append(f"  - Approved Longs Hit Rate:    {self.hit_rate_approved_longs:.1%} (beat {self.benchmark_ticker})")
            lines.append(f"  - Approved Longs Mean Alpha:  {self.mean_alpha_approved_longs:+.2%}")
        else:
            lines.append("  - Approved Longs Alpha:       No settled approved positions")
        lines.append(f"  - Passed Decisions Mean Alpha:{self.mean_alpha_passed_discipline:+.2%}")
        lines.append("")
        lines.append("## 3. Forensic & Capital Safety Safeguards")
        lines.append(f"  - High Manipulation Risks:    {self.forensic_high_risk_count} flagged by Beneish/Sloan")
        if self.forensic_high_risk_count > 0:
            lines.append(f"  - High-Risk Realized Return:  {self.forensic_high_risk_mean_return:+.2%}")
        lines.append(f"  - Bear Floor Downside Breaches: {self.bear_floor_breach_count}")
        lines.append("=" * 72)
        return "\n".join(lines)


def summarize_backtest(
    records: list[BacktestDecisionRecord],
    forward_days: int = 90,
    benchmark_ticker: str = "SPY",
) -> BacktestSummary:
    """Aggregate decision records and compute hit rate, alpha, and forensic safety stats."""
    total = len(records)
    approved_longs = 0
    passed_discipline = 0
    validation_watch = 0
    settled_count = 0
    pending_count = 0

    approved_alphas: list[float] = []
    passed_alphas: list[float] = []
    bear_floor_breaches = 0
    high_risk_returns: list[float] = []
    high_risk_count = 0

    for rec in records:
        v = (rec.verdict or "").upper()
        if "APPROVED" in v:
            approved_longs += 1
        elif "PASSED" in v:
            passed_discipline += 1
        elif "WATCH" in v or "NO_POSITION" in v:
            validation_watch += 1

        is_high_risk = (rec.forensic_verdict or "").upper() == "HIGH_MANIPULATION_RISK"
        if is_high_risk:
            high_risk_count += 1

        # Settlement
        settle = settle_decision(rec.ticker, rec.as_of_date, forward_days=forward_days, benchmark_ticker=benchmark_ticker)
        if settle.get("status") == "settled":
            settled_count += 1
            alpha = float(settle["alpha_pct"]) / 100.0
            ret = float(settle["asset_return_pct"]) / 100.0
            end_px = float(settle["end_price"])

            if "APPROVED" in v:
                approved_alphas.append(alpha)
                # Check if downside bear floor was breached
                if rec.bear_floor and end_px < rec.bear_floor:
                    bear_floor_breaches += 1
            else:
                passed_alphas.append(alpha)

            if is_high_risk:
                high_risk_returns.append(ret)
        elif settle.get("status") == "pending_settlement":
            pending_count += 1

    hit_rate = (
        sum(1 for a in approved_alphas if a > 0) / len(approved_alphas)
        if approved_alphas else None
    )
    mean_approved_alpha = (sum(approved_alphas) / len(approved_alphas)) if approved_alphas else 0.0
    mean_passed_alpha = (sum(passed_alphas) / len(passed_alphas)) if passed_alphas else 0.0
    mean_high_risk_ret = (sum(high_risk_returns) / len(high_risk_returns)) if high_risk_returns else 0.0

    return BacktestSummary(
        total_runs=total,
        approved_longs=approved_longs,
        passed_discipline=passed_discipline,
        validation_watch=validation_watch,
        settled_runs=settled_count,
        pending_settlement=pending_count,
        hit_rate_approved_longs=hit_rate,
        mean_alpha_approved_longs=mean_approved_alpha,
        mean_alpha_passed_discipline=mean_passed_alpha,
        bear_floor_breach_count=bear_floor_breaches,
        forensic_high_risk_count=high_risk_count,
        forensic_high_risk_mean_return=mean_high_risk_ret,
        forward_days=forward_days,
        benchmark_ticker=benchmark_ticker,
    )


def run_backtest_grid(
    tickers: list[str],
    start_date: str,
    end_date: str,
    every_n_days: int = 30,
    cases_root: Path | str = "cases/backtests",
    forward_days: int = 90,
    model: Any | None = None,
    budget_max_tool_calls: int = 25,
) -> tuple[list[BacktestDecisionRecord], BacktestSummary]:
    """Execute a backtest sweep across tickers and historical dates."""
    dates = generate_date_grid(start_date, end_date, every_n_days=every_n_days)
    records: list[BacktestDecisionRecord] = []

    for ticker in tickers:
        clean_t = ticker.strip().upper()
        for d in dates:
            logger.info("Running backtest cell for %s as of %s", clean_t, d)
            try:
                rec = run_backtest_cell(
                    ticker=clean_t,
                    as_of_date=d,
                    cases_root=cases_root,
                    model=model,
                    budget_max_tool_calls=budget_max_tool_calls,
                )
                records.append(rec)
            except Exception as exc:
                logger.error("Backtest cell failed for %s on %s: %s", clean_t, d, exc)
                records.append(
                    BacktestDecisionRecord(
                        ticker=clean_t,
                        as_of_date=d,
                        case_id="failed",
                        status=f"error: {exc}",
                    )
                )

    summary = summarize_backtest(records, forward_days=forward_days)
    return records, summary
