"""Tests for deterministic SEC XBRL financials extraction."""
from unittest.mock import patch, MagicMock
import pytest
from app.sec.financials import get_sec_financials, SecFinancialsResult


def _mock_xbrl_data():
    return {
        "periods": ["2026-Q2", "2026-Q1", "2025-Q4", "2025-Q3"],
        "revenue": {"2026-Q2": 7_500_000_000, "2026-Q1": 6_800_000_000, "2025-Q4": 6_200_000_000, "2025-Q3": 5_800_000_000},
        "gross_profit": {"2026-Q2": 2_400_000_000, "2026-Q1": 2_040_000_000, "2025-Q4": 1_736_000_000, "2025-Q3": 1_508_000_000},
        "operating_income": {"2026-Q2": 900_000_000, "2026-Q1": 750_000_000, "2025-Q4": 600_000_000, "2025-Q3": 500_000_000},
        "net_income": {"2026-Q2": 700_000_000, "2026-Q1": 600_000_000, "2025-Q4": 450_000_000, "2025-Q3": 380_000_000},
        "cash_and_equivalents": {"2026-Q2": 8_000_000_000, "2026-Q1": 7_500_000_000, "2025-Q4": 7_000_000_000, "2025-Q3": 6_500_000_000},
        "total_debt": {"2026-Q2": 5_000_000_000, "2026-Q1": 5_200_000_000, "2025-Q4": 5_500_000_000, "2025-Q3": 5_800_000_000},
        "inventory": {"2026-Q2": 3_100_000_000, "2026-Q1": 3_500_000_000, "2025-Q4": 3_800_000_000, "2025-Q3": 4_000_000_000},
        "capex": {"2026-Q2": 1_200_000_000, "2026-Q1": 1_100_000_000, "2025-Q4": 1_000_000_000, "2025-Q3": 950_000_000},
    }


def test_get_sec_financials_success():
    with patch("app.sec.financials._fetch_xbrl_statements", return_value=_mock_xbrl_data()):
        result = get_sec_financials("MU")

    assert isinstance(result, SecFinancialsResult)
    assert result.ticker == "MU"
    assert result.status == "ok"
    assert len(result.periods) == 4

    # Check Gross Margin % calculation: 2400 / 7500 = 32%
    assert result.gross_margin_pct["2026-Q2"] == pytest.approx(0.32)
    assert result.gross_margin_pct["2026-Q1"] == pytest.approx(0.30)
    assert result.gross_margin_pct["2025-Q4"] == pytest.approx(0.28)
    assert result.gross_margin_pct["2025-Q3"] == pytest.approx(0.26)

    # Check Inventory QoQ change: (3100 - 3500) / 3500 = -11.4% drawdown (demand absorption!)
    assert result.inventory_qoq_change_pct["2026-Q2"] == pytest.approx(-0.1143, abs=1e-3)

    # Check Net Cash: 8000M cash - 5000M debt = +3000M net cash
    assert result.net_cash["2026-Q2"] == pytest.approx(3_000_000_000)


def test_get_sec_financials_unavailable_on_error():
    with patch("app.sec.financials._fetch_xbrl_statements", side_effect=Exception("No XBRL found")):
        result = get_sec_financials("SKETCHY")

    assert result.ticker == "SKETCHY"
    assert result.status == "unavailable"
    assert result.periods == ()
    assert "No XBRL found" in result.error_message


def test_sec_financials_serialization_round_trip():
    with patch("app.sec.financials._fetch_xbrl_statements", return_value=_mock_xbrl_data()):
        result = get_sec_financials("MU")

    d = result.to_dict()
    restored = SecFinancialsResult.from_dict(d)
    assert restored == result
