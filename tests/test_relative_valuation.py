"""Unit tests for relative valuation and peer multiple analysis."""
from __future__ import annotations

import pytest

from app.market.relative_valuation import (
    calculate_historical_percentiles,
    calculate_peer_rankings,
)
from app.market.schemas import (
    CompanyMultipleSnapshot,
    MultiplePercentileStat,
    PeerCompsResult,
)


def test_calculate_historical_percentiles_forensic_filtering():
    """Negative and non-positive multiples from loss-making quarters must be filtered out."""
    # Historical quarterly P/E with some negative/zero quarters
    measures = {
        "PeRatio": {
            "2023-12-31": 25.0,
            "2023-09-30": -15.0,  # Negative: should be filtered
            "2023-06-30": 20.0,
            "2023-03-31": 0.0,    # Zero: should be filtered
            "2022-12-31": 30.0,
            "2022-09-30": 35.0,
        }
    }
    # Current P/E is 22.0
    snapshot = CompanyMultipleSnapshot(
        ticker="TEST",
        company_name="Test Corp",
        market_cap=10_000_000_000.0,
        trailing_pe=22.0,
        forward_pe=18.0,
        ev_to_ebitda=14.0,
        ev_to_sales=4.0,
        price_to_book=5.0,
        fcf_yield=0.045,
        operating_margin=0.20,
        revenue_growth=0.15,
        as_of="2026-10-25",
    )

    stats = calculate_historical_percentiles(measures, snapshot)
    pe_stat = stats["trailing_pe"]

    assert pe_stat.status == "ok"
    # Filtered valid history: [25.0, 20.0, 30.0, 35.0] (4 positive quarters)
    assert pe_stat.lookback_periods == 4
    assert pe_stat.min_value == 20.0
    assert pe_stat.max_value == 35.0
    assert pe_stat.median_value == 27.5
    # 22.0 is greater than 20.0 (1 out of 4), so percentile is around 25%-37.5%
    assert pe_stat.percentile is not None
    assert 20.0 <= pe_stat.percentile <= 40.0
    assert pe_stat.regime == "fair"


def test_calculate_peer_rankings_and_medians():
    """Peer medians, ranks, and percentage spreads must compute correctly."""
    target = CompanyMultipleSnapshot(
        ticker="TARGET",
        company_name="Target Inc",
        market_cap=50_000_000_000.0,
        trailing_pe=15.0,
        forward_pe=12.0,
        ev_to_ebitda=10.0,
        ev_to_sales=2.5,
        price_to_book=3.0,
        fcf_yield=0.06,
        operating_margin=0.18,
        revenue_growth=0.12,
        as_of="2026-10-25",
    )
    peers = [
        CompanyMultipleSnapshot(
            ticker="PEER1", company_name="Peer 1", market_cap=40_000_000_000.0,
            trailing_pe=20.0, forward_pe=16.0, ev_to_ebitda=12.0, ev_to_sales=3.0,
            price_to_book=4.0, fcf_yield=0.04, operating_margin=0.15, revenue_growth=0.10,
            as_of="2026-10-25",
        ),
        CompanyMultipleSnapshot(
            ticker="PEER2", company_name="Peer 2", market_cap=60_000_000_000.0,
            trailing_pe=25.0, forward_pe=20.0, ev_to_ebitda=15.0, ev_to_sales=4.0,
            price_to_book=5.0, fcf_yield=0.03, operating_margin=0.22, revenue_growth=0.18,
            as_of="2026-10-25",
        ),
        CompanyMultipleSnapshot(
            ticker="PEER3", company_name="Peer 3", market_cap=30_000_000_000.0,
            trailing_pe=10.0, forward_pe=8.0, ev_to_ebitda=7.0, ev_to_sales=1.5,
            price_to_book=2.0, fcf_yield=0.08, operating_margin=0.12, revenue_growth=0.05,
            as_of="2026-10-25",
        ),
    ]

    medians, ranks, pcts, spreads = calculate_peer_rankings(target, peers)

    # Peer trailing_pe values: [10.0, 20.0, 25.0] -> median is 20.0
    assert medians["trailing_pe"] == 20.0
    # Target trailing_pe is 15.0: ranks 2nd (between 10.0 and 20.0)
    assert ranks["trailing_pe"] == 2
    # Spread vs median: (15.0 - 20.0) / 20.0 = -0.25 (-25% discount)
    assert spreads["trailing_pe"] == -0.25

    # Target fcf_yield is 0.06: peer values [0.04, 0.03, 0.08] -> median 0.04
    assert medians["fcf_yield"] == 0.04


def test_peer_comps_result_serialization():
    """PeerCompsResult should serialize to and from dict idempotently."""
    target = CompanyMultipleSnapshot(
        ticker="AAPL", company_name="Apple Inc.", market_cap=3_000_000_000_000.0,
        trailing_pe=30.0, forward_pe=26.0, ev_to_ebitda=22.0, ev_to_sales=7.5,
        price_to_book=40.0, fcf_yield=0.035, operating_margin=0.30, revenue_growth=0.08,
        as_of="2026-10-25",
    )
    result = PeerCompsResult(
        target_ticker="AAPL",
        peer_tickers=("MSFT", "GOOGL"),
        target_multiples=target,
        peer_multiples=(target,),
        peer_medians={"trailing_pe": 28.0},
        target_peer_ranks={"trailing_pe": 2},
        target_peer_percentiles={"trailing_pe": 50.0},
        target_median_spreads={"trailing_pe": 0.071},
        historical_percentiles={
            "trailing_pe": MultiplePercentileStat(
                metric_name="trailing_pe",
                current_value=30.0,
                min_value=22.0,
                max_value=36.0,
                median_value=28.5,
                percentile=60.0,
                z_score=0.45,
                lookback_periods=12,
                regime="fair",
                status="ok",
            )
        },
        provider="yfinance+finnhub",
        as_of="2026-10-25",
    )

    d = result.to_dict()
    assert d["target_ticker"] == "AAPL"
    assert d["peer_medians"]["trailing_pe"] == 28.0

    restored = PeerCompsResult.from_dict(d)
    assert restored.target_ticker == "AAPL"
    assert restored.historical_percentiles["trailing_pe"].regime == "fair"
