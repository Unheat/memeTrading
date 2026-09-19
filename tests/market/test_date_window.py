"""Tests for Point-in-Time date windowing and clamping adapted from donor."""
from datetime import datetime, timezone, timedelta
import pytest

from app.market.date_window import as_of, in_window, coverage_gap, to_utc


def test_to_utc():
    naive = datetime(2023, 5, 1, 12, 0, 0)
    aware = to_utc(naive)
    assert aware.tzinfo == timezone.utc


def test_as_of_live_mode_unrestricted():
    # In live research (run_as_of_date=None), requested date passes through unchanged
    assert as_of("2026-05-01", run_as_of_date=None) == "2026-05-01"
    assert as_of(None, run_as_of_date=None) is None


def test_as_of_backtest_clamping():
    # In backtest mode (run_as_of_date='2023-06-01')
    # Requested date earlier than cutoff is allowed
    assert as_of("2023-01-01", run_as_of_date="2023-06-01") == "2023-01-01"
    # Requested date later than cutoff is clamped to cutoff
    assert as_of("2024-01-01", run_as_of_date="2023-06-01") == "2023-06-01"
    # None requested defaults to cutoff
    assert as_of(None, run_as_of_date="2023-06-01") == "2023-06-01"


def test_in_window_live_mode_allows_undated():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 12, 31, tzinfo=timezone.utc)

    # In live research mode (run_as_of_date=None), undated items are preserved
    assert in_window(pub_dt=None, start_dt=start, end_dt=end, run_as_of_date=None) is True

    # Dated item inside window
    inside = datetime(2026, 6, 1, tzinfo=timezone.utc)
    assert in_window(pub_dt=inside, start_dt=start, end_dt=end, run_as_of_date=None) is True

    # Dated item outside window
    outside = datetime(2025, 1, 1, tzinfo=timezone.utc)
    assert in_window(pub_dt=outside, start_dt=start, end_dt=end, run_as_of_date=None) is False


def test_in_window_backtest_mode_drops_undated_live_artifacts():
    # Historical backtest in 2023
    start = datetime(2023, 1, 1, tzinfo=timezone.utc)
    end = datetime(2023, 6, 1, tzinfo=timezone.utc)

    # In historical mode, undated live web artifacts are dropped to prevent lookahead leak
    assert in_window(pub_dt=None, start_dt=start, end_dt=end, run_as_of_date="2023-06-01") is False

    # Historical item within 2023 window is kept
    inside_2023 = datetime(2023, 3, 15, tzinfo=timezone.utc)
    assert in_window(pub_dt=inside_2023, start_dt=start, end_dt=end, run_as_of_date="2023-06-01") is True

    # Future item (2024) is rejected
    future_2024 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    assert in_window(pub_dt=future_2024, start_dt=start, end_dt=end, run_as_of_date="2023-06-01") is False


def test_coverage_gap_detects_truncated_vendor_feed():
    # Vendor only has items starting 2026-08-01, but backtest requested 2024-01-01 to 2024-06-01
    recent_dates = [datetime(2026, 8, 15, tzinfo=timezone.utc)]
    gap_msg = coverage_gap(
        dates=recent_dates,
        start_date="2024-01-01",
        end_date="2024-06-01",
        source="RedditFeed",
        subject="sentiment",
    )
    assert gap_msg is not None
    assert "RedditFeed unavailable for 2024-01-01..2024-06-01" in gap_msg
    assert "not an absence of sentiment" in gap_msg
