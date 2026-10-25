"""Unit tests for compare_candidates tool with InjectedState."""
from __future__ import annotations

import json
import pytest

from app.agent.tools import create_agent_tools


def test_compare_candidates_returns_populated_comparison_cards():
    """Tool must return populated comparison cards from state rather than a hollow stub."""
    tools = create_agent_tools()
    compare_tool = next(t for t in tools if t.name == "compare_candidates")

    injected_state = {
        "candidates": {
            "cand_aapl": {
                "ticker": "AAPL",
                "company": "Apple Inc.",
                "market_context": {"quote": {"price": 220.0}},
                "sec_financials": {
                    "periods": ["2024-Q3"],
                    "revenue": {"2024-Q3": 95_000_000_000.0},
                    "gross_margin_pct": {"2024-Q3": 46.0},
                    "operating_margin_pct": {"2024-Q3": 30.0},
                    "net_cash": {"2024-Q3": 50_000_000_000.0},
                    "capex": {"2024-Q3": 3_000_000_000.0},
                    "fcf": {"2024-Q3": 25_000_000_000.0},
                },
            },
            "cand_msft": {
                "ticker": "MSFT",
                "company": "Microsoft Corp",
                "market_context": {"quote": {"price": 420.0}},
                "sec_financials": {
                    "periods": ["2024-Q3"],
                    "revenue": {"2024-Q3": 65_000_000_000.0},
                    "gross_margin_pct": {"2024-Q3": 69.0},
                    "operating_margin_pct": {"2024-Q3": 44.0},
                    "net_cash": {"2024-Q3": 70_000_000_000.0},
                    "capex": {"2024-Q3": 14_000_000_000.0},
                    "fcf": {"2024-Q3": 19_000_000_000.0},
                },
            },
        }
    }

    raw = compare_tool.invoke({
        "candidate_ids": ["cand_aapl", "cand_msft"],
        "metrics": ["price", "revenue", "operating_margin"],
        "injected_state": injected_state,
    })

    res = json.loads(raw)
    assert res["status"] == "ok"
    assert "comparisons" in res
    cards = res["comparisons"]
    assert len(cards) == 3

    price_card = next(c for c in cards if c["metric_key"] == "price")
    assert price_card["candidate_values"]["AAPL"]["value"] == 220.0
    assert price_card["candidate_values"]["MSFT"]["value"] == 420.0

    rev_card = next(c for c in cards if c["metric_key"] == "revenue")
    assert rev_card["candidate_values"]["AAPL"]["value"] == 95_000_000_000.0
    assert rev_card["candidate_values"]["MSFT"]["value"] == 65_000_000_000.0

    opm_card = next(c for c in cards if c["metric_key"] == "operating_margin")
    assert opm_card["candidate_values"]["AAPL"]["value"] == 30.0
    assert opm_card["candidate_values"]["MSFT"]["value"] == 44.0
