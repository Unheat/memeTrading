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
        "cash_from_operations": {"2026-Q2": 2_000_000_000, "2026-Q1": 1_800_000_000, "2025-Q4": 1_600_000_000, "2025-Q3": 1_500_000_000},
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


def test_sort_period_cols_orders_chronologically_descending():
    from app.sec.financials import _sort_period_cols
    cols = ["2024-03-31", "2024-09-30", "2024-06-30", "2023-12-31"]
    sorted_cols = _sort_period_cols(cols)
    assert sorted_cols == ["2024-09-30", "2024-06-30", "2024-03-31", "2023-12-31"]


def test_resolve_bs_dataframe_and_col_maps_q4_to_annual_fy():
    """Verify quarterly Q4 column maps to annual FY column on Form 10-K balance sheet."""
    import pandas as pd
    from app.sec.financials import _resolve_bs_dataframe_and_col, _find_bs_metric

    bs_q = pd.DataFrame(
        {"Q3 2026": [30.0], "Q2 2026": [25.0]},
        index=["CashAndCashEquivalentsAtCarryingValue"],
    )
    bs_a = pd.DataFrame(
        {
            "FY 2026": [75.0, 10.0, 30.0],
            "FY 2025": [70.0, 9.0, 31.0],
        },
        index=[
            "CashCashEquivalentsAndShortTermInvestments",
            "LongTermDebtCurrent",
            "LongTermDebtNoncurrent",
        ],
    )

    df_q, col_q = _resolve_bs_dataframe_and_col("Q3 2026", bs_q, bs_a)
    assert df_q is bs_q
    assert col_q == "Q3 2026"

    df_q4, col_q4 = _resolve_bs_dataframe_and_col("Q4 2026", bs_q, bs_a)
    assert df_q4 is bs_a
    assert col_q4 == "FY 2026"

    cash = _find_bs_metric(["CashCashEquivalentsAndShortTermInvestments"], "Q4 2026", bs_q, bs_a)
    assert cash == 75.0

    st_debt = _find_bs_metric(["LongTermDebtCurrent"], "Q4 2026", bs_q, bs_a)
    lt_debt = _find_bs_metric(["LongTermDebtNoncurrent"], "Q4 2026", bs_q, bs_a)
    assert st_debt == 10.0
    assert lt_debt == 30.0
