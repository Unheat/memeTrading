# ADR-005: Deterministic Investment Committee Governance ("Conviction Requests, Risk Disposes") & 3-Way Debate

## Status
Accepted

## Date
2026-10-18

## Context
In earlier versions of the research agent, final capital allocation and position recommendations were influenced by model prose outputs or ad-hoc heuristic win probability adjustments (+0.04 for clean forensic, -0.06 for objections). Furthermore, when evaluating high-conviction ideas, single-perspective model reasoning tended to exhibit confirmation bias, under-weighting downside tails or liquidity bottlenecks.

## Decision
Separate model qualitative deliberation from capital allocation through deterministic risk governance and adversarial debate:
1. **"Conviction Requests, Risk Disposes" Architecture**:
   - Adapted from `reference/ai-hedge-fund/hedge_fund/risk/limits.py` (`apply_limits`).
   - The LLM synthesizes qualitative rationale, thesis breakers, and scenario context.
   - Deterministic arithmetic computes Fractional Kelly sizing and clamps position weight against hard fund mandates:
     * Standard Single-Name Cap: 10.0% of portfolio.
     * High Conviction Tier Cap: 15.0% of portfolio.
     * Maximum Loss Budget: 5.0% of portfolio equity ($\text{Weight} \times \text{Downside \%} \le 0.05$).
   - Strict Non-Redistribution Rule: Exposure trimmed by a risk clamp is *never* redistributed to other names; it remains in cash.
   - All clamps emit immutable `ClampEvent` logs on the `ICVerdict` for compliance auditing.
2. **3-Way Multi-Perspective Risk Debate Context**:
   - Adapted from `reference/tradingagents/tradingagents/agents/risk_mgmt/` (`conservative_debator`, `aggressive_debator`, `neutral_debator`).
   - Before the Chief Investment Officer (CIO) renders the final decision, three explicit stances are synthesized:
     * **Conservative Analyst**: Demands capital preservation, stresses downside risk to the bear floor, and cites forensic red flags.
     * **Aggressive Analyst**: Highlights operating leverage, channel acceleration, and multi-quarter catalyst upside.
     * **Neutral Analyst**: Reconciles the 3:1 reward-to-risk ratio against the institutional hurdle.
3. **Synchronized Report Hierarchy**:
   - Research reports (`memo.md`) lead with the Investment Committee's authoritative deliberation table, conviction tier, and CIO summary at the top of `## Executive Allocation & Research Synthesis`, ensuring intermediate analyst chat never contradicts or obscures the final Boardroom verdict.

## Alternatives Considered

### Allowing LLM to Author Position Percentages Directly
- Pros: Simple prompt instruction.
- Cons: Prone to hallucinating arbitrary portfolio allocations without respect to downside volatility, variance, or fund mandate limits.
- Rejected: Incompatible with institutional fiduciary standards.

### Single-Prompt Committee Deliberation
- Pros: Fewer LLM generation steps.
- Cons: Suffers from one-track confirmation bias, easily swayed by whichever evidence was retrieved last.
- Rejected: Multi-perspective adversarial debate produces far more robust and defensive decisions.

## Consequences
- Capital allocation is mathematically constrained and provably risk-bounded.
- Every position reduction is transparently logged via `clamp_events`.
- Executive memos provide an unambiguous, non-contradictory synthesis of the investment decision.
