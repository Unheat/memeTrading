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

    # Check Deterministic DIO and DSO
    # COGS = 7500M - 2400M = 5100M. DIO = (3100 / 5100) * 91.25 = 55.5 days
    assert result.dio["2026-Q2"] == pytest.approx(55.5, abs=0.1)
    # DSO = (1500 / 7500) * 91.25 = 18.25 days
    assert result.dso["2026-Q2"] == pytest.approx(18.25, abs=0.1)

    # Check FCF & TTM FCF: (2000-1200) + (1800-1100) + (1600-1000) + (1500-950) = 800 + 700 + 600 + 550 = 2650M
    assert result.fcf["2026-Q2"] == pytest.approx(800_000_000)
    assert result.ttm_fcf == pytest.approx(2_650_000_000)


def test_discrete_cash_flows_preserved_without_double_decumulation():
    """Verify discrete quarterly cash flows (like Google Q4 CFO or Meta Q2 CapEx) are not mangled."""
    from app.sec.financials import _compute_ttm_fcf

    periods = ["Q2 2026", "Q1 2026", "Q4 2025", "Q3 2025"]
    fcf = {
        "Q2 2026": -5_855_000_000.0,
        "Q1 2026": 10_116_000_000.0,
        "Q4 2025": 24_551_000_000.0,  # Discrete Q4: 52.4B CFO - 27.85B CapEx
        "Q3 2025": 24_461_000_000.0,  # Discrete Q3: 48.4B CFO - 23.95B CapEx
    }
    ttm = _compute_ttm_fcf(fcf, periods)
    assert ttm == pytest.approx(53_273_000_000.0)


def test_gross_profit_derived_from_cogs_when_concept_absent():
    """Verify single-step filers (like Amazon) have Gross Profit derived from Revenue - COGS."""
    import pandas as pd
    from app.sec.financials import _find_row_val

    df = pd.DataFrame(
        {
            "Q2 2026": [200_000_000_000.0, 95_000_000_000.0],
        },
        index=["RevenueFromContractWithCustomerExcludingAssessedTax", "CostOfGoodsAndServicesSold"],
    )

    rev = _find_row_val(df, ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenue"], "Q2 2026")
    gp = _find_row_val(df, ["GrossProfit", "GrossMargin"], "Q2 2026")
    cogs = _find_row_val(df, ["CostOfGoodsAndServicesSold", "CostOfRevenue"], "Q2 2026")

    assert rev == 200_000_000_000.0
    assert gp is None
    assert cogs == 95_000_000_000.0

    derived_gp = round(rev - cogs, 2)
    assert derived_gp == 105_000_000_000.0
    gm_pct = round(derived_gp / rev, 4)
    assert gm_pct == 0.525


def test_sort_period_cols_handles_mixed_date_and_quarter_formats():
    """Verify _sort_period_cols handles ISO dates without colliding with Q1 and without TypeErrors."""
    from app.sec.financials import _sort_period_cols

    cols = ["2024-12-31", "Q4 2024", "Q1 2025", "2025-Q2", "FY 2024", "2024-06-30", "Q3 2024"]
    sorted_cols = _sort_period_cols(cols)
    assert sorted_cols == ["2025-Q2", "Q1 2025", "2024-12-31", "Q4 2024", "Q3 2024", "2024-06-30", "FY 2024"]


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


def _capex_fact(concept: str, fiscal_year: int, fiscal_period: str, start, end, value):
    """Build a minimal edgartools-like fact for CapEx fallback tests."""
    from types import SimpleNamespace

    return SimpleNamespace(
        concept=concept,
        period_type="duration",
        fiscal_year=fiscal_year,
        fiscal_period=fiscal_period,
        period_start=start,
        period_end=end,
        value=value,
        filing_date=end,
    )


def _capex_fallback_company(facts):
    """Build a minimal company object exposing only .facts for the fallback extractor."""
    from types import SimpleNamespace

    return SimpleNamespace(facts=facts)


def test_fact_quarterly_capex_derives_q2_from_ytd_h1():
    """NVDA-style filings tag Q2 CapEx only as a 181-day H1 YTD fact; derive Q2 = H1 - Q1."""
    from datetime import date

    from app.sec.financials import _extract_fact_quarterly_capex

    company = _capex_fallback_company([
        _capex_fact(
            "us-gaap:PaymentsToAcquireProductiveAssets", 2027, "Q1",
            date(2026, 1, 26), date(2026, 4, 26), 1_757_000_000.0,
        ),
        _capex_fact(
            "us-gaap:PaymentsToAcquireProductiveAssets", 2027, "Q2",
            date(2026, 1, 26), date(2026, 7, 26), 4_434_000_000.0,
        ),
    ])
    result = _extract_fact_quarterly_capex(company, ["Q2 2027"])
    assert result["Q2 2027"] == round(4_434_000_000.0 - 1_757_000_000.0, 2)


def test_fact_quarterly_capex_derives_q3_from_ytd_9m():
    """Q3 CapEx reported only inside a 272-day 9M YTD fact derives as 9M - H1."""
    from datetime import date

    from app.sec.financials import _extract_fact_quarterly_capex

    company = _capex_fallback_company([
        _capex_fact(
            "us-gaap:PaymentsToAcquireProductiveAssets", 2026, "Q2",
            date(2025, 1, 27), date(2025, 7, 27), 3_122_000_000.0,
        ),
        _capex_fact(
            "us-gaap:PaymentsToAcquireProductiveAssets", 2026, "Q3",
            date(2025, 1, 27), date(2025, 10, 26), 4_758_000_000.0,
        ),
    ])
    result = _extract_fact_quarterly_capex(company, ["Q3 2026"])
    assert result["Q3 2026"] == round(4_758_000_000.0 - 3_122_000_000.0, 2)


def test_fact_quarterly_capex_q4_still_derives_fy_minus_9m():
    """Pre-existing Q4 derivation (FY - 9M) keeps working alongside Q2/Q3 derivation."""
    from datetime import date

    from app.sec.financials import _extract_fact_quarterly_capex

    company = _capex_fallback_company([
        _capex_fact(
            "us-gaap:PaymentsToAcquireProductiveAssets", 2026, "Q3",
            date(2025, 1, 27), date(2025, 10, 26), 4_758_000_000.0,
        ),
        _capex_fact(
            "us-gaap:PaymentsToAcquireProductiveAssets", 2026, "FY",
            date(2025, 1, 26), date(2026, 1, 25), 6_042_000_000.0,
        ),
    ])
    result = _extract_fact_quarterly_capex(company, ["Q4 2026"])
    assert result["Q4 2026"] == round(6_042_000_000.0 - 4_758_000_000.0, 2)


def test_fact_quarterly_capex_undeducible_stays_absent():
    """A YTD H1 fact without a Q1 base must NOT be invented as the discrete quarter."""
    from datetime import date

    from app.sec.financials import _extract_fact_quarterly_capex

    company = _capex_fallback_company([
        _capex_fact(
            "us-gaap:PaymentsToAcquireProductiveAssets", 2027, "Q2",
            date(2026, 1, 26), date(2026, 7, 26), 4_434_000_000.0,
        ),
    ])
    result = _extract_fact_quarterly_capex(company, ["Q2 2027"])
    assert "Q2 2027" not in result
