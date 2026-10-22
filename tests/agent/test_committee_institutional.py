"""Unit tests for institutional committee risk governance and debate architecture.

Covers:
  - Deterministic risk limits clamping (apply_risk_limits)
  - Immutable ClampEvent audit logging
  - 3-way risk debate perspectives (Conservative, Aggressive, Neutral)
  - End-to-end ICVerdict risk integration
"""
from __future__ import annotations

import pytest

from app.agent.committee import apply_risk_limits, generate_risk_debate_context


def test_apply_risk_limits_clamps_excessive_kelly():
    """Proposed allocation exceeding fund cap is clamped and logged."""
    # Proposed 25% allocation on standard tier (cap 10%)
    clamped_weight, clamps = apply_risk_limits(
        proposed_allocation=0.25,
        ticker="XYZ",
        conviction_tier="MEDIUM CONVICTION 🔥🔥",
        downside_pct=0.15,
        max_position_cap=0.10,
    )
    assert clamped_weight == 0.10
    assert len(clamps) == 1
    assert clamps[0]["limit"] == "max_position_pct"
    assert clamps[0]["before"] == 0.25
    assert clamps[0]["after"] == 0.10


def test_apply_risk_limits_enforces_loss_budget():
    """High downside risk on large allocation is clamped to protect 5% fund loss budget."""
    # Proposed 12% allocation with 50% downside risk -> potential loss = 6% > 5% budget
    clamped_weight, clamps = apply_risk_limits(
        proposed_allocation=0.12,
        ticker="VOLATILE",
        conviction_tier="HIGH CONVICTION 🔥🔥🔥",
        downside_pct=0.50,
        max_high_conviction_cap=0.15,
        max_loss_budget=0.05,
    )
    # 5% loss budget / 50% downside = 10% maximum allocation
    assert clamped_weight == 0.10
    assert any(c["limit"] == "max_loss_budget" for c in clamps)


def test_generate_risk_debate_context_synthesizes_perspectives():
    """3-way debate context provides distinct Conservative, Aggressive, and Neutral stances."""
    debate = generate_risk_debate_context(
        ticker="MU",
        current_price=100.0,
        base_target=160.0,
        bear_floor=80.0,
        ratio=3.0,
        bull_report=None,
        adversarial=None,
        ch_verdict="CHANNEL_ACCELERATION",
        forensic={"red_flags": ["High CapEx cycle"]},
    )
    assert "conservative_analyst" in debate
    assert "aggressive_analyst" in debate
    assert "neutral_analyst" in debate

    assert "Conservative" in debate["conservative_analyst"]
    assert "Aggressive" in debate["aggressive_analyst"]
    assert "Neutral" in debate["neutral_analyst"]
    assert "CHANNEL_ACCELERATION" in debate["aggressive_analyst"] or "channel" in debate["aggressive_analyst"].lower()
