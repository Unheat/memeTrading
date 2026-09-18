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
        "total_assets": {"2026-Q2": 20_000_000_000, "2026-Q1": 19_500_000_000, "2025-Q4": 19_000_000_000, "2025-Q3": 18_500_000_000},
        "accounts_receivable": {"2026-Q2": 1_500_000_000, "2026-Q1": 1_400_000_000, "2025-Q4": 1_300_000_000, "2025-Q3": 1_200_000_000},
        "current_assets": {"2026-Q2": 13_000_000_000, "2026-Q1": 12_500_000_000, "2025-Q4": 12_000_000_000, "2025-Q3": 11_500_000_000},
        "ppe": {"2026-Q2": 6_000_000_000, "2026-Q1": 5_800_000_000, "2025-Q4": 5_500_000_000, "2025-Q3": 5_300_000_000},
        "depreciation": {"2026-Q2": 500_000_000, "2026-Q1": 480_000_000, "2025-Q4": 460_000_000, "2025-Q3": 450_000_000},
        "sg_and_a": {"2026-Q2": 1_000_000_000, "2026-Q1": 950_000_000, "2025-Q4": 900_000_000, "2025-Q3": 850_000_000},
        "stock_based_compensation": {"2026-Q2": 150_000_000, "2026-Q1": 140_000_000, "2025-Q4": 130_000_000, "2025-Q3": 120_000_000},
        "current_liabilities": {"2026-Q2": 3_500_000_000, "2026-Q1": 3_400_000_000, "2025-Q4": 3_300_000_000, "2025-Q3": 3_200_000_000},
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

    # Check Forensic balance sheet & cash flow concepts
    assert result.total_assets["2026-Q2"] == pytest.approx(20_000_000_000)
    assert result.accounts_receivable["2026-Q2"] == pytest.approx(1_500_000_000)
    assert result.current_assets["2026-Q2"] == pytest.approx(13_000_000_000)
    assert result.ppe["2026-Q2"] == pytest.approx(6_000_000_000)
    assert result.depreciation["2026-Q2"] == pytest.approx(500_000_000)
    assert result.sg_and_a["2026-Q2"] == pytest.approx(1_000_000_000)
    assert result.stock_based_compensation["2026-Q2"] == pytest.approx(150_000_000)
    assert result.current_liabilities["2026-Q2"] == pytest.approx(3_500_000_000)

    # Check FCF & TTM FCF: (2000-1200) + (1800-1100) + (1600-1000) + (1500-950) = 800 + 700 + 600 + 550 = 2650M
    assert result.fcf["2026-Q2"] == pytest.approx(800_000_000)
    assert result.ttm_fcf == pytest.approx(2_650_000_000)


def test_decumulate_cash_flows_unaccumulates_ytd():
    """Verify cumulative YTD Form 10-Q figures are de-cumulated into discrete quarters."""
    from app.sec.financials import _decumulate_cash_flows

    periods = ["2026-Q3", "2026-Q2", "2026-Q1"]
    cumulative_cfo = {
        "2026-Q1": 1_000_000_000.0,
        "2026-Q2": 2_100_000_000.0,  # 6M YTD
        "2026-Q3": 3_250_000_000.0,  # 9M YTD
    }

    discrete_cfo = _decumulate_cash_flows(periods, cumulative_cfo)
    assert discrete_cfo["2026-Q1"] == pytest.approx(1_000_000_000.0)
    assert discrete_cfo["2026-Q2"] == pytest.approx(1_100_000_000.0)  # 2100 - 1000
    assert discrete_cfo["2026-Q3"] == pytest.approx(1_150_000_000.0)  # 3250 - 2100


def test_decumulate_cash_flows_leaves_discrete_alone():
    """Verify already-discrete figures are not subtracted."""
    from app.sec.financials import _decumulate_cash_flows

    periods = ["2026-Q3", "2026-Q2", "2026-Q1"]
    discrete_cfo = {
        "2026-Q1": 1_000_000_000.0,
        "2026-Q2": 1_050_000_000.0,
        "2026-Q3": 1_100_000_000.0,
    }

    result = _decumulate_cash_flows(periods, discrete_cfo)
    assert result == discrete_cfo


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
