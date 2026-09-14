"""Tests for FRED macro provider."""
from unittest.mock import patch
import pytest
from app.market.providers.fred import (
    API_KEY_ENV,
    get_macro_series,
    get_macro_context,
)


def _fred_payload() -> dict:
    # FRED returns sort_order=desc: newest first.
    return {
        "observations": [
            {"date": "2026-09-03", "value": "4.05"},
            {"date": "2026-09-02", "value": "4.02"},
            {"date": "2026-09-01", "value": "."},        # missing value skipped
        ]
    }


def test_fred_unconfigured_returns_empty():
    with patch.dict("os.environ", {}, clear=True):
        assert get_macro_series("DGS10") == []


def test_fred_series_maps_and_skips_missing():
    with patch.dict("os.environ", {API_KEY_ENV: "k"}):
        with patch("app.market.providers.fred._fred_get", return_value=_fred_payload()):
            obs = get_macro_series("DGS10")
    assert obs == [
        {"date": "2026-09-02", "value": 4.02},
        {"date": "2026-09-03", "value": 4.05},
    ]  # oldest -> newest


def test_fred_context_latest_and_unavailable():
    def _fake_get(path: str, params: dict) -> dict:
        if params["series_id"] == "DGS10":
            return _fred_payload()
        raise Exception("down")

    with patch.dict("os.environ", {API_KEY_ENV: "k"}):
        with patch("app.market.providers.fred._fred_get", side_effect=_fake_get):
            ctx = get_macro_context(["DGS10", "BAMLH0A0HYM2"])
    assert ctx["DGS10"]["latest_value"] == 4.05
    assert ctx["DGS10"]["latest_date"] == "2026-09-03"
    assert ctx["DGS10"]["status"] == "ok"
    assert ctx["BAMLH0A0HYM2"]["status"] == "unavailable"


def test_fred_context_requires_series_ids():
    with pytest.raises(ValueError):
        get_macro_context([])
