"""Relative valuation and peer multiple analysis engine.

Calculates:
- Peer comps matrix: EV/EBITDA, EV/Sales, Forward P/E, Trailing P/E, FCF Yield.
- Peer medians, percentile rankings, and median premium/discount spreads.
- Historical multiple distribution percentiles (3-5 year range) with forensic negative-value filtering.
"""
from __future__ import annotations

import datetime
import math
from typing import Any, Mapping, Sequence

from app.market.provider import (
    fetch_historical_valuation_measures,
    fetch_multiples_snapshot,
)
from app.market.providers.finnhub import FinnhubClient
from app.market.schemas import (
    CompanyMultipleSnapshot,
    MultiplePercentileStat,
    PeerCompsResult,
)

METRIC_MAP = {
    "trailing_pe": ("PeRatio", "trailing_pe"),
    "forward_pe": ("ForwardPeRatio", "forward_pe"),
    "ev_to_ebitda": ("EnterprisesValueEBITDARatio", "ev_to_ebitda"),
    "ev_to_sales": ("EnterprisesValueRevenueRatio", "ev_to_sales"),
    "price_to_book": ("PbRatio", "price_to_book"),
    "price_to_sales": ("PsRatio", "price_to_sales"),
}


def _median(values: Sequence[float]) -> float | None:
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2 == 1:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2.0


def calculate_historical_percentiles(
    measures: Mapping[str, Mapping[str, float]],
    current_snapshot: CompanyMultipleSnapshot | None = None,
    lookback_periods: int = 20,
) -> dict[str, MultiplePercentileStat]:
    """Calculate historical percentiles and z-scores for valuation multiples.

    Forensic guard: Filters out non-positive multiples (loss-making quarters) so negative values
    do not distort distribution percentiles or median benchmarks.
    """
    stats: dict[str, MultiplePercentileStat] = {}

    for norm_name, (yahoo_key, attr_name) in METRIC_MAP.items():
        # Match yahoo_key case-insensitively
        series_dict: Mapping[str, float] = {}
        for k, v in measures.items():
            if k.lower() == yahoo_key.lower():
                series_dict = v
                break

        # Collect historical series
        raw_values: list[float] = []
        for period_col, val in series_dict.items():
            if period_col.lower() == "current":
                continue
            if val is not None and math.isfinite(val) and val > 0:
                raw_values.append(float(val))

        # Truncate to lookback_periods
        hist = raw_values[:lookback_periods]

        # Determine current value
        curr_val = getattr(current_snapshot, attr_name, None) if current_snapshot else None
        if curr_val is None and "Current" in series_dict:
            c = series_dict["Current"]
            if c is not None and math.isfinite(c) and c > 0:
                curr_val = float(c)

        if len(hist) < 4 or curr_val is None or curr_val <= 0:
            stats[norm_name] = MultiplePercentileStat(
                metric_name=norm_name,
                current_value=curr_val,
                min_value=min(hist) if hist else None,
                max_value=max(hist) if hist else None,
                median_value=_median(hist),
                percentile=None,
                z_score=None,
                lookback_periods=len(hist),
                regime="insufficient_history",
                status="unavailable",
            )
            continue

        min_v = min(hist)
        max_v = max(hist)
        med_v = _median(hist)

        # Percentile ranking of current value vs historical distribution
        strictly_less = sum(1 for x in hist if x < curr_val)
        equal = sum(1 for x in hist if abs(x - curr_val) < 1e-4)
        pct = round(((strictly_less + 0.5 * equal) / len(hist)) * 100.0, 1)

        mean_v = sum(hist) / len(hist)
        variance = sum((x - mean_v) ** 2 for x in hist) / len(hist)
        std_v = math.sqrt(variance) if variance > 1e-6 else None
        z_score = round((curr_val - mean_v) / std_v, 2) if std_v else 0.0

        if pct < 25.0:
            regime = "discount"
        elif pct <= 75.0:
            regime = "fair"
        else:
            regime = "premium"

        stats[norm_name] = MultiplePercentileStat(
            metric_name=norm_name,
            current_value=curr_val,
            min_value=min_v,
            max_value=max_v,
            median_value=med_v,
            percentile=pct,
            z_score=z_score,
            lookback_periods=len(hist),
            regime=regime,
            status="ok",
        )

    return stats


def calculate_peer_rankings(
    target: CompanyMultipleSnapshot,
    peers: Sequence[CompanyMultipleSnapshot],
) -> tuple[dict[str, float | None], dict[str, int | None], dict[str, float | None], dict[str, float | None]]:
    """Compute peer medians, target ranks, percentiles, and median spreads."""
    metrics = ("trailing_pe", "forward_pe", "ev_to_ebitda", "ev_to_sales", "price_to_book", "fcf_yield")

    peer_medians: dict[str, float | None] = {}
    target_ranks: dict[str, int | None] = {}
    target_pcts: dict[str, float | None] = {}
    target_spreads: dict[str, float | None] = {}

    for m in metrics:
        target_val = getattr(target, m, None)
        valid_peer_vals = [
            getattr(p, m) for p in peers
            if getattr(p, m, None) is not None and math.isfinite(getattr(p, m)) and (m == "fcf_yield" or getattr(p, m) > 0)
        ]

        if not valid_peer_vals:
            peer_medians[m] = None
            target_ranks[m] = None
            target_pcts[m] = None
            target_spreads[m] = None
            continue

        med = _median(valid_peer_vals)
        peer_medians[m] = round(med, 2) if med is not None else None

        if target_val is not None and math.isfinite(target_val) and (m == "fcf_yield" or target_val > 0):
            # Rank 1 is lowest multiple / cheapest
            rank = 1 + sum(1 for p in valid_peer_vals if p < target_val)
            pct = round((sum(1 for p in valid_peer_vals if p < target_val) / len(valid_peer_vals)) * 100.0, 1)
            spread = round((target_val - med) / med, 3) if med and med != 0 else None

            target_ranks[m] = rank
            target_pcts[m] = pct
            target_spreads[m] = spread
        else:
            target_ranks[m] = None
            target_pcts[m] = None
            target_spreads[m] = None

    return peer_medians, target_ranks, target_pcts, target_spreads


def get_relative_valuation(
    ticker: str,
    peer_tickers: Sequence[str] | None = None,
    max_peers: int = 8,
    finnhub_client: FinnhubClient | None = None,
    as_of_date: str | None = None,
) -> PeerCompsResult:
    """Orchestrate peer discovery, multiples fetching, and historical percentile analysis."""
    clean_ticker = ticker.strip().upper()
    as_of = str(as_of_date or datetime.date.today().isoformat())

    # 1. Discover Peers
    peers_list: list[str] = []
    if peer_tickers:
        peers_list = [p.strip().upper() for p in peer_tickers if p.strip().upper() != clean_ticker]
    else:
        # Finnhub peers
        fh = finnhub_client or FinnhubClient()
        if fh.is_configured:
            discovered = fh.get_company_peers(clean_ticker)
            peers_list = [p for p in discovered if p != clean_ticker]

    peers_list = list(dict.fromkeys(peers_list))[:max_peers]

    # 2. Fetch Multiples for Target
    target_raw = fetch_multiples_snapshot(clean_ticker)
    target_snapshot = CompanyMultipleSnapshot(
        ticker=clean_ticker,
        company_name=target_raw.get("company_name"),
        market_cap=target_raw.get("market_cap"),
        trailing_pe=target_raw.get("trailing_pe"),
        forward_pe=target_raw.get("forward_pe"),
        ev_to_ebitda=target_raw.get("ev_to_ebitda"),
        ev_to_sales=target_raw.get("ev_to_sales"),
        price_to_book=target_raw.get("price_to_book"),
        fcf_yield=target_raw.get("fcf_yield"),
        operating_margin=target_raw.get("operating_margin"),
        revenue_growth=target_raw.get("revenue_growth"),
        as_of=as_of,
    )

    # 3. Fetch Multiples for Peers
    peer_snapshots: list[CompanyMultipleSnapshot] = []
    for pt in peers_list:
        try:
            praw = fetch_multiples_snapshot(pt)
            peer_snapshots.append(
                CompanyMultipleSnapshot(
                    ticker=pt,
                    company_name=praw.get("company_name"),
                    market_cap=praw.get("market_cap"),
                    trailing_pe=praw.get("trailing_pe"),
                    forward_pe=praw.get("forward_pe"),
                    ev_to_ebitda=praw.get("ev_to_ebitda"),
                    ev_to_sales=praw.get("ev_to_sales"),
                    price_to_book=praw.get("price_to_book"),
                    fcf_yield=praw.get("fcf_yield"),
                    operating_margin=praw.get("operating_margin"),
                    revenue_growth=praw.get("revenue_growth"),
                    as_of=as_of,
                )
            )
        except Exception:
            continue

    # 4. Peer Rankings and Medians
    peer_medians, target_ranks, target_pcts, target_spreads = calculate_peer_rankings(
        target_snapshot, peer_snapshots
    )

    # 5. Historical Percentiles
    hist_measures = fetch_historical_valuation_measures(clean_ticker, periods=20)
    hist_percentiles = calculate_historical_percentiles(hist_measures, target_snapshot)

    return PeerCompsResult(
        target_ticker=clean_ticker,
        peer_tickers=tuple(p.ticker for p in peer_snapshots),
        target_multiples=target_snapshot,
        peer_multiples=tuple(peer_snapshots),
        peer_medians=peer_medians,
        target_peer_ranks=target_ranks,
        target_peer_percentiles=target_pcts,
        target_median_spreads=target_spreads,
        historical_percentiles=hist_percentiles,
        provider="yfinance+finnhub",
        as_of=as_of,
    )
