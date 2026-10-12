"""Tests for phantom inventory hoarding / bullwhip over-ordering detection."""
from unittest.mock import MagicMock
import pytest
from app.agent.specialists import run_channel_check_analysis
from app.agent.expectations import _classify_expectation_arbitrage


def test_phantom_inventory_triggers_warning_and_verdict():
    """Verify that bullish channel lead times paired with DIO > 135d and inventory surge > 15% trigger SUSPECTED_PHANTOM_INVENTORY_HOARDING."""
    state = {
        "ticker": "MU",
        "channel_check_receipts": [
            {
                "receipt_id": "cc_dist_01",
                "channel_type": "distributor_inventory",
                "source_url_or_channel": "https://distributor.com/audit",
                "observed_metric": "lead_times_weeks",
                "observed_value": 26,
                "baseline_value": 12,
                "implication": "bullish_inflection",
                "tier": "tier_2_distribution",
                "grade": "grade_a_hard_metric",
            },
            {
                "receipt_id": "cc_spot_02",
                "channel_type": "spot_pricing",
                "source_url_or_channel": "https://dramexchange.com/spot",
                "observed_metric": "spot_contract_spread_pct",
                "observed_value": 25.0,
                "implication": "bullish_inflection",
                "tier": "tier_1_physical_core",
                "grade": "grade_a_hard_metric",
            },
            {
                "receipt_id": "cc_dist_03",
                "channel_type": "distributor_inventory",
                "source_url_or_channel": "https://distributor.com/buffers",
                "observed_metric": "channel_inventory_weeks",
                "observed_value": 3.0,
                "implication": "bullish_inflection",
                "tier": "tier_2_distribution",
                "grade": "grade_b_action",
            },
        ],
        "sec_financials": {
            "status": "ok",
            "periods": ["2026-Q1", "2025-Q4"],
            "dio": {"2026-Q1": 148.5, "2025-Q4": 120.0},
            "inventory_qoq_change_pct": {"2026-Q1": 0.22, "2025-Q4": 0.05},
        },
    }

    res = run_channel_check_analysis(state)
    report = res["channel_check_report"]

    assert report["channel_verdict"] == "SUSPECTED_PHANTOM_INVENTORY_HOARDING"
    assert "WARNING: Suspected phantom inventory hoarding" in report["synthesis_summary"]
    assert "148.5d > 135d" in report["synthesis_summary"]
    assert "22.0% > 15%" in report["synthesis_summary"]


def test_clean_inventory_allows_genuine_channel_acceleration():
    """Verify that when DIO is healthy (<= 135d) or inventory is contracting, genuine acceleration is confirmed."""
    state = {
        "ticker": "MU",
        "channel_check_receipts": [
            {
                "receipt_id": "cc_dist_01",
                "channel_type": "distributor_inventory",
                "source_url_or_channel": "https://distributor.com/audit",
                "observed_metric": "lead_times_weeks",
                "observed_value": 26,
                "baseline_value": 12,
                "implication": "bullish_inflection",
                "tier": "tier_2_distribution",
                "grade": "grade_a_hard_metric",
            },
            {
                "receipt_id": "cc_spot_02",
                "channel_type": "spot_pricing",
                "source_url_or_channel": "https://dramexchange.com/spot",
                "observed_metric": "spot_contract_spread_pct",
                "observed_value": 25.0,
                "implication": "bullish_inflection",
                "tier": "tier_1_physical_core",
                "grade": "grade_a_hard_metric",
            },
            {
                "receipt_id": "cc_dist_03",
                "channel_type": "distributor_inventory",
                "source_url_or_channel": "https://distributor.com/buffers",
                "observed_metric": "channel_inventory_weeks",
                "observed_value": 3.0,
                "implication": "bullish_inflection",
                "tier": "tier_2_distribution",
                "grade": "grade_b_action",
            },
        ],
        "sec_financials": {
            "status": "ok",
            "periods": ["2026-Q1", "2025-Q4"],
            "dio": {"2026-Q1": 124.8, "2025-Q4": 121.8},
            "inventory_qoq_change_pct": {"2026-Q1": -0.018, "2025-Q4": -0.05},
        },
    }

    res = run_channel_check_analysis(state)
    report = res["channel_check_report"]

    assert report["channel_verdict"] == "CHANNEL_ACCELERATION"


def test_arbitrage_classifier_phantom_inventory_blocks_unpriced_acceleration():
    """Verify expectation arbitrage never treats phantom hoarding as unpriced acceleration."""
    delta, verdict = _classify_expectation_arbitrage(
        channel=None,
        implied=0.03,
        consensus=0.08,
        channel_verdict="SUSPECTED_PHANTOM_INVENTORY_HOARDING",
    )
    assert verdict != "UNPRICED_CHANNEL_ACCELERATION"
    assert verdict == "UNCERTAIN_DISPERSION"

    delta, verdict_perfection = _classify_expectation_arbitrage(
        channel=None,
        implied=0.22,
        consensus=0.18,
        channel_verdict="SUSPECTED_PHANTOM_INVENTORY_HOARDING",
    )
    assert verdict_perfection == "PRICED_TO_PERFECTION"
