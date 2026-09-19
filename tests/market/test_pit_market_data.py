"""Tests for Point-in-Time filtering across market data and SEC filings."""
import pandas as pd
import pytest
from app.market.provider import fetch_history
from app.market.market_data import get_market_data
from app.sec.acquisition import list_sec_filings


class FakeFiling:
    def __init__(self, form: str, filing_date: str, accession_no: str) -> None:
        self.form = form
        self.filing_date = filing_date
        self.accession_no = accession_no
        self.url = f"https://www.sec.gov/Archives/{accession_no}-index.html"


class FakeCompany:
    cik = 123456

    def __init__(self, filings: list[FakeFiling]) -> None:
        self._filings = filings

    def get_filings(self, **kwargs):
        return self._filings


def test_list_sec_filings_pit_until_filters_future_filings():
    company = FakeCompany([
        FakeFiling("10-K", "2023-12-15", "0000123456-23-000001"),
        FakeFiling("10-Q", "2024-03-31", "0000123456-24-000001"),
        FakeFiling("10-Q", "2024-06-30", "0000123456-24-000002"),
    ])

    # Case 1: Live mode (until is None) -> all 3 filings returned
    res_live = list_sec_filings("xyz", until=None, company_factory=lambda t: company)
    assert len(res_live.filings) == 3

    # Case 2: Historical PIT mode (until="2024-04-15") -> 2024-06-30 filing filtered out
    res_pit = list_sec_filings("xyz", until="2024-04-15", company_factory=lambda t: company)
    assert len(res_pit.filings) == 2
    dates = [f.filing_date.strftime("%Y-%m-%d") for f in res_pit.filings]
    assert "2024-06-30" not in dates
    assert "2024-03-31" in dates
    assert "2023-12-15" in dates


def test_fetch_history_pit_filters_future_bars(monkeypatch):
    # Mock _yf_history
    dates = pd.date_range("2024-01-01", periods=10, freq="D")
    df = pd.DataFrame({
        "Open": [100.0] * 10,
        "High": [105.0] * 10,
        "Low": [95.0] * 10,
        "Close": [100.0 + i for i in range(10)],
        "Volume": [1000.0] * 10,
    }, index=dates)

    monkeypatch.setattr("app.market.provider._yf_history", lambda t, p: df)

    # Live mode: all 10 bars
    res_live = fetch_history("NVDA", as_of_date=None)
    assert len(res_live["dates"]) == 10

    # PIT cutoff at day 5 (2024-01-05)
    res_pit = fetch_history("NVDA", as_of_date="2024-01-05")
    assert len(res_pit["dates"]) == 5
    assert res_pit["dates"][-1][:10] == "2024-01-05"
    assert res_pit["close"][-1] == 104.0
