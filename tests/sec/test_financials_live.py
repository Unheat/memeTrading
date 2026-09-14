"""Tests for edgartools XBRL dataframe parsing in app/sec/financials.py."""
import pandas as pd
from unittest.mock import patch, MagicMock
import pytest
from app.sec.financials import _fetch_xbrl_statements, _find_row_val, _is_period_col


def test_is_period_col():
    assert _is_period_col("2026-06-30") is True
    assert _is_period_col("2025-12-31") is True
    assert _is_period_col("concept") is False
    assert _is_period_col("label") is False
    assert _is_period_col("unit") is False


def test_find_row_val():
    df = pd.DataFrame(
        {
            "concept": ["Revenues", "GrossProfit", "OperatingIncomeLoss"],
            "2026-06-30": [8_000_000_000.0, 2_800_000_000.0, 1_000_000_000.0],
            "2026-03-31": [7_000_000_000.0, 2_100_000_000.0, 800_000_000.0],
        }
    ).set_index("concept")

    val = _find_row_val(df, ["Revenues", "Revenue"], "2026-06-30")
    assert val == 8_000_000_000.0

    val_gp = _find_row_val(df, ["GrossProfit"], "2026-03-31")
    assert val_gp == 2_100_000_000.0

    assert _find_row_val(df, ["NonExistentConcept"], "2026-06-30") is None


def test_fetch_xbrl_statements_with_mocked_company():
    inc_df = pd.DataFrame(
        {
            "2026-06-30": [8_000_000_000.0, 2_800_000_000.0, 1_000_000_000.0, 800_000_000.0],
            "2026-03-31": [7_000_000_000.0, 2_100_000_000.0, 800_000_000.0, 600_000_000.0],
        },
        index=["Revenues", "GrossProfit", "OperatingIncomeLoss", "NetIncomeLoss"],
    )

    bs_df = pd.DataFrame(
        {
            "2026-06-30": [5_000_000_000.0, 3_000_000_000.0, 1_000_000_000.0, 2_000_000_000.0],
            "2026-03-31": [4_500_000_000.0, 3_500_000_000.0, 1_000_000_000.0, 2_200_000_000.0],
        },
        index=["CashAndCashEquivalentsAtCarryingValue", "InventoryNet", "ShortTermBorrowings", "LongTermDebtNoncurrent"],
    )

    cf_df = pd.DataFrame(
        {
            "2026-06-30": [-1_200_000_000.0],
            "2026-03-31": [-1_100_000_000.0],
        },
        index=["PaymentsToAcquirePropertyPlantAndEquipment"],
    )

    mock_company = MagicMock()
    mock_company.income_statement.return_value = inc_df
    mock_company.balance_sheet.return_value = bs_df
    mock_company.cash_flow_statement.return_value = cf_df

    with patch("app.sec.financials._get_company", return_value=mock_company), \
         patch("app.sec.identity.ensure_sec_identity", return_value="TestAgent test@example.com"):
        data = _fetch_xbrl_statements("MU", periods=2)

    assert data["periods"] == ["2026-06-30", "2026-03-31"]
    assert data["revenue"]["2026-06-30"] == 8_000_000_000.0
    assert data["gross_profit"]["2026-06-30"] == 2_800_000_000.0
    assert data["cash_and_equivalents"]["2026-06-30"] == 5_000_000_000.0
    assert data["total_debt"]["2026-06-30"] == 3_000_000_000.0  # 1000 + 2000
    assert data["inventory"]["2026-06-30"] == 3_000_000_000.0
    assert data["capex"]["2026-06-30"] == 1_200_000_000.0  # positive magnitude
