#!/usr/bin/env python3
"""CLI utility to execute historical backtest sweeps across tickers and dates.

Usage:
    python scripts/run_backtest.py --tickers NVDA AAPL MSFT --start-date 2023-01-01 --end-date 2023-06-01 --step-days 60
    python scripts/run_backtest.py --tickers MU --start-date 2024-01-01 --end-date 2024-04-01 --step-days 30 --forward-days 60
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from app.config import load_config
from app.evaluation.backtest import run_backtest_grid


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Historical Point-in-Time Backtest Evaluation Harness",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--tickers",
        "-t",
        nargs="+",
        required=True,
        help="One or more stock tickers to evaluate (e.g. NVDA AAPL MSFT)",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        required=True,
        help="Starting historical analysis date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        required=True,
        help="Ending historical analysis date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--step-days",
        type=int,
        default=30,
        help="Step size between evaluation dates in days",
    )
    parser.add_argument(
        "--forward-days",
        type=int,
        default=90,
        help="Forward settlement evaluation horizon in calendar days (e.g. 30, 60, 90)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="cases/backtests",
        help="Directory to persist historical investigation cases",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable detailed debug logging",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    print("=" * 72)
    print(" 🚀 RUNNING HISTORICAL POINT-IN-TIME BACKTEST SWEEP")
    print("=" * 72)
    print(f"• Tickers:       {', '.join(t.upper() for t in args.tickers)}")
    print(f"• Grid Range:    {args.start_date} to {args.end_date} (every {args.step_days} days)")
    print(f"• Horizon:       {args.forward_days} days vs SPY benchmark")
    print(f"• Output Cases:  {args.output_dir}")
    print("-" * 72)

    try:
        records, summary = run_backtest_grid(
            tickers=args.tickers,
            start_date=args.start_date,
            end_date=args.end_date,
            every_n_days=args.step_days,
            cases_root=args.output_dir,
            forward_days=args.forward_days,
        )
        print("\n" + summary.render() + "\n")
        return 0
    except Exception as exc:
        print(f"\n❌ Backtest sweep failed: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
