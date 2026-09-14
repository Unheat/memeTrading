"""Tests for get_company_research: mocked yfinance seams, per-section degradation."""
from unittest.mock import patch
import pytest
from app.market.company_research import (
    get_company_research,
    CompanyResearchResult,
    _yf_price_targets,
    _yf_recommendations,
    _yf_estimates,
    _yf_calendar,
)


def _price_targets() -> dict:
    return {"low": 90.0, "mean": 130.0, "high": 180.0, "current": 122.0}


def _recommendations():
    """Fake first row of yfinance recommendations frame."""
    return {"strongBuy": 12, "buy": 20, "hold": 9, "sell": 2, "strongSell": 1}


def _estimates(ticker: str, metric: str):
    if metric == "eps":
        return {
            "0y": {"avg": 3.20, "low": 2.90, "high": 3.55, "numberOfAnalysts": 44, "growth": 0.21},
            "+1y": {"avg": 3.90, "low": 3.10, "high": 4.60, "numberOfAnalysts": 44, "growth": 0.22},
        }
    return {
        "0y": {"avg": 42.1e9, "low": 40.0e9, "high": 44.5e9, "numberOfAnalysts": 38, "growth": 0.18},
    }


def _calendar() -> dict:
    return {"Earnings Date": ["2026-10-28", "2026-11-02"]}


def test_get_company_research_full_coverage():
    with patch("app.market.company_research._yf_price_targets", return_value=_price_targets()), \
         patch("app.market.company_research._yf_recommendations", return_value=_recommendations()), \
         patch("app.market.company_research._yf_estimates", side_effect=_estimates), \
         patch("app.market.company_research._yf_calendar", return_value=_calendar()):
        result = get_company_research("MU")

    assert isinstance(result, CompanyResearchResult)
    assert result.ticker == "MU"
    assert result.provider == "yfinance"

    assert result.price_targets is not None
    assert result.price_targets.mean.value == 130.0
    assert result.price_targets.low.value == 90.0
    assert result.price_targets.high.status == "ok"

    assert result.ratings is not None
    assert result.ratings.buy == 20
    assert result.ratings.total == 44

    assert len(result.eps_estimates) == 2
    assert result.eps_estimates[0].metric == "eps"
    assert result.eps_estimates[0].avg == 3.20
    assert result.eps_estimates[0].n_analysts == 44
    assert len(result.revenue_estimates) == 1

    assert result.next_earnings_date == "2026-10-28"
    assert result.days_until_earnings is not None
    assert result.earnings_proximity_flag in ("SAFE", "CAUTION", "BLACKOUT_RISK")


def test_earnings_proximity_flag_logic():
    from datetime import datetime, timezone, timedelta
    from app.market.company_research import _calculate_earnings_proximity

    today = datetime.now(timezone.utc).date()
    in_3_days = (today + timedelta(days=3)).isoformat()
    in_10_days = (today + timedelta(days=10)).isoformat()
    in_30_days = (today + timedelta(days=30)).isoformat()

    days, flag = _calculate_earnings_proximity(in_3_days)
    assert days == 3
    assert flag == "BLACKOUT_RISK"

    days, flag = _calculate_earnings_proximity(in_10_days)
    assert days == 10
    assert flag == "CAUTION"

    days, flag = _calculate_earnings_proximity(in_30_days)
    assert days == 30
    assert flag == "SAFE"

    days, flag = _calculate_earnings_proximity(None)
    assert days is None
    assert flag == "UNKNOWN"


def test_get_company_research_no_coverage_degrades_to_unavailable():
    with patch("app.market.company_research._yf_price_targets", return_value={}), \
         patch("app.market.company_research._yf_recommendations", return_value=None), \
         patch("app.market.company_research._yf_estimates", return_value={}), \
         patch("app.market.company_research._yf_calendar", return_value={}):
        result = get_company_research("SKETCHY")

    assert result.price_targets is None
    assert result.ratings is None
    assert result.eps_estimates == ()
    assert result.revenue_estimates == ()
    assert result.next_earnings_date is None


def test_get_company_research_section_failures_isolated():
    with patch("app.market.company_research._yf_price_targets", side_effect=Exception("boom")), \
         patch("app.market.company_research._yf_recommendations", return_value=_recommendations()), \
         patch("app.market.company_research._yf_estimates", side_effect=_estimates), \
         patch("app.market.company_research._yf_calendar", side_effect=Exception("down")):
        result = get_company_research("MU")

    assert result.price_targets is None          # degraded silently
    assert result.ratings is not None            # unaffected
    assert len(result.eps_estimates) == 2        # unaffected
    assert result.next_earnings_date is None     # degraded silently


def test_company_research_result_round_trip():
    with patch("app.market.company_research._yf_price_targets", return_value=_price_targets()), \
         patch("app.market.company_research._yf_recommendations", return_value=_recommendations()), \
         patch("app.market.company_research._yf_estimates", side_effect=_estimates), \
         patch("app.market.company_research._yf_calendar", return_value=_calendar()):
        result = get_company_research("MU")

    restored = CompanyResearchResult.from_dict(result.to_dict())
    assert restored == result


def test_get_company_research_rejects_bad_ticker():
    with pytest.raises(ValueError):
        get_company_research("")
    with pytest.raises(ValueError):
        get_company_research("nv da")


def test_seams_exist_for_patch_points():
    assert callable(_yf_price_targets)
    assert callable(_yf_recommendations)
    assert callable(_yf_estimates)
    assert callable(_yf_calendar)
