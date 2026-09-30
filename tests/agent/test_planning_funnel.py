"""Unit tests for the deterministic screening shortlist (funnel first cut)."""
from __future__ import annotations

import pytest

from app.agent.planning import (
    build_deterministic_shortlist,
    _parse_analyst_rating,
    PlannerScoutQuery,
)


def _row(ticker: str, mcap: float | None, fwd_pe: float | None, rating: str | None) -> dict:
    return {
        "ticker": ticker,
        "company": f"{ticker} Inc.",
        "market_cap": mcap,
        "trailing_pe": None,
        "forward_pe": fwd_pe,
        "analyst_rating": rating,
    }


def test_parse_analyst_rating() -> None:
    """Verify yfinance consensus rating parsing ('2.3 Buy (15)' -> (2.3, 15))."""
    assert _parse_analyst_rating("2.3 Buy (15)") == (2.3, 15)
    assert _parse_analyst_rating("1.5 Strong Buy (42)") == (1.5, 42)
    assert _parse_analyst_rating("3.8 Hold") == (3.8, None)
    assert _parse_analyst_rating(None) == (None, None)
    assert _parse_analyst_rating("garbage") == (None, None)


def test_shortlist_prefers_cheap_valuation_and_bullish_consensus() -> None:
    """The composite should rank a cheap, well-covered stock above an expensive one."""
    rows = [
        _row("CHEAP", 50e9, 12.0, "1.8 Strong Buy (30)"),
        _row("PRICEY", 50e9, 90.0, "4.2 Underperform (5)"),
    ]
    shortlist = build_deterministic_shortlist(rows, top_n=8)
    assert [r["ticker"] for r in shortlist] == ["CHEAP", "PRICEY"]
    assert shortlist[0]["composite_score"] > shortlist[1]["composite_score"]
    # Two-row pool: CHEAP maxes both factors (cheapest P/E, most bullish consensus)
    assert shortlist[0]["value_score"] == pytest.approx(1.0)
    assert shortlist[0]["conviction_score"] == pytest.approx(1.0)


def test_shortlist_hard_gates_drop_insufficient_rows() -> None:
    """Rows missing market cap or every valuation multiple are dropped."""
    rows = [
        _row("GOOD", 10e9, 15.0, "2.0 Buy (10)"),
        _row("NOMCAP", None, 15.0, "2.0 Buy (10)"),   # no market cap -> dropped
        _row("NOPE", 5e9, None, "2.0 Buy (10)"),      # no PEs at all -> dropped
    ]
    shortlist = build_deterministic_shortlist(rows, top_n=8)
    assert [r["ticker"] for r in shortlist] == ["GOOD"]


def test_shortlist_missing_rating_gets_neutral_conviction() -> None:
    """A missing analyst rating receives the neutral percentile, not a zero."""
    rows = [
        _row("RATED", 10e9, 20.0, "2.0 Buy (10)"),
        _row("UNRATED", 10e9, 20.0, None),
    ]
    shortlist = build_deterministic_shortlist(rows, top_n=8)
    by_ticker = {r["ticker"]: r for r in shortlist}
    assert by_ticker["UNRATED"]["conviction_score"] == pytest.approx(0.5)
    # Identical value and size -> rated (more bullish conviction) wins
    assert by_ticker["RATED"]["composite_score"] > by_ticker["UNRATED"]["composite_score"]


def test_shortlist_size_contribution_favors_liquidity() -> None:
    """All else equal, the larger (more liquid) name scores higher on the size factor."""
    rows = [
        _row("MEGA", 2_000e9, 25.0, "2.5 Buy (20)"),
        _row("SMALL", 2e9, 25.0, "2.5 Buy (20)"),
    ]
    shortlist = build_deterministic_shortlist(rows, top_n=8)
    by_ticker = {r["ticker"]: r for r in shortlist}
    assert by_ticker["MEGA"]["size_score"] > by_ticker["SMALL"]["size_score"]
    assert shortlist[0]["ticker"] == "MEGA"


def test_shortlist_respects_top_n_and_determinism() -> None:
    """Output is capped at top_n and identical inputs produce identical order."""
    rows = [
        _row(f"T{i:02d}", (30 - i) * 1e9, 10.0 + i, f"2.{i % 9} Buy ({40 - i})")
        for i in range(15)
    ]
    first = build_deterministic_shortlist(rows, top_n=8)
    second = build_deterministic_shortlist(rows, top_n=8)
    assert len(first) == 8
    assert [r["ticker"] for r in first] == [r["ticker"] for r in second]
    scores = [r["composite_score"] for r in first]
    assert scores == sorted(scores, reverse=True)


def test_shortlist_empty_and_fallback_trailing_pe() -> None:
    """Empty pool returns empty; forward P/E missing falls back to trailing P/E."""
    assert build_deterministic_shortlist([], top_n=8) == []

    rows = [
        {"ticker": "A", "company": "A", "market_cap": 5e9, "trailing_pe": 9.0, "forward_pe": None, "analyst_rating": "2.0 Buy (8)"},
        {"ticker": "B", "company": "B", "market_cap": 5e9, "trailing_pe": 40.0, "forward_pe": None, "analyst_rating": "2.0 Buy (8)"},
    ]
    shortlist = build_deterministic_shortlist(rows, top_n=8)
    assert shortlist[0]["ticker"] == "A"  # cheaper trailing P/E wins via fallback


def test_scout_query_limit_schema_bounds() -> None:
    """PlannerScoutQuery.limit enforces 1..20 via schema validation."""
    q = PlannerScoutQuery(tool_name="screen_stocks", preset="growth_technology_stocks", limit=20)
    assert q.limit == 20
    with pytest.raises(Exception):
        PlannerScoutQuery(tool_name="screen_stocks", limit=50)
    with pytest.raises(Exception):
        PlannerScoutQuery(tool_name="search_web", limit=0)


def test_shortlist_4_pillar_momentum_and_quality() -> None:
    """Verify momentum (52W position) and operating margin quality are reflected in scores."""
    rows = [
        {
            "ticker": "HIGH_MOM",
            "company": "High Momentum Inc",
            "price": 95.0,
            "fifty_two_week_high": 100.0,
            "fifty_two_week_low": 50.0,
            "market_cap": 20e9,
            "forward_pe": 25.0,
            "analyst_rating": "2.0 Buy (15)",
            "operating_margin": 0.28,
        },
        {
            "ticker": "LOW_MOM",
            "company": "Falling Knife Corp",
            "price": 52.0,
            "fifty_two_week_high": 100.0,
            "fifty_two_week_low": 50.0,
            "market_cap": 20e9,
            "forward_pe": 25.0,
            "analyst_rating": "2.0 Buy (15)",
            "operating_margin": 0.05,
        },
    ]
    shortlist = build_deterministic_shortlist(rows, top_n=8)
    by_ticker = {r["ticker"]: r for r in shortlist}
    assert by_ticker["HIGH_MOM"]["momentum_score"] > by_ticker["LOW_MOM"]["momentum_score"]
    assert by_ticker["HIGH_MOM"]["quality_score"] > by_ticker["LOW_MOM"]["quality_score"]
    assert shortlist[0]["ticker"] == "HIGH_MOM"


def test_candidate_allocation_schema() -> None:
    """Verify CandidateAllocation is part of ResearchPlanSchema."""
    from app.agent.planning import CandidateAllocation, ResearchPlanSchema

    alloc = CandidateAllocation(ticker="NVDA", priority="tier1_deep", focus_mandate="CapEx ROI")
    assert alloc.priority == "tier1_deep"
    plan = ResearchPlanSchema(
        brief="Test",
        candidate_entities=["NVDA"],
        candidate_allocations=[alloc],
    )
    assert len(plan.candidate_allocations) == 1
    assert plan.candidate_allocations[0].ticker == "NVDA"


def test_research_request_auto_routes_conversational_ticker_to_query() -> None:
    """When a user passes a sentence/query in the ticker field, normalize ticker to None and treat as query."""
    from app.agent.state import ResearchRequest

    req = ResearchRequest(
        ticker="FIND ME BEST TECH STOCK TO INVEST RIGHT NOW",
        query="",
    )
    assert req.ticker is None
    assert req.query == "FIND ME BEST TECH STOCK TO INVEST RIGHT NOW"
    intent = req.resolve_intent()
    assert intent.requires_candidate_workspaces is True

    # Real single ticker remains unaffected
    req_real = ResearchRequest(
        ticker="NVDA",
        query="Forensic balance sheet audit",
    )
    assert req_real.ticker == "NVDA"
    assert req_real.query == "Forensic balance sheet audit"


