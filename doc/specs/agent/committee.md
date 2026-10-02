# Module Spec — `app/agent/committee.py`

## Responsibility

Act as Chief Investment Officer (CIO) and Chair of the Investment Committee: weigh Bull thesis against Adversarial Bear Red Team, enforce Pre-Trade Risk Gates, evaluate 3:1 Asymmetry Hurdle, apply Passing Discipline, calculate Fractional Kelly position sizing, audit candidate winners in screening mode, and issue top-down macroeconomic regime directives.

## Public Contracts

### `ICVerdict`
- `ticker: str` (non-empty uppercase)
- `verdict: str` (`"APPROVED_LONG_HIGH"`, `"APPROVED_LONG_MEDIUM"`, `"VALIDATION_WATCH"`, `"PAPER_TRADE_WATCH"`, `"PASSED_STRICT_DISCIPLINE"`)
- `conviction_tier: str` (`"HIGH CONVICTION 🔥🔥🔥"`, `"MEDIUM CONVICTION 🔥🔥"`, `"VALIDATION 🔥"`, `"PAPER TRADE 📋"`, `"PASSED 🚫"`)
- `reward_to_risk_ratio: float | None` (computed as `(base_target - price) / (price - bear_floor)`)
- `kelly_position_size_pct: float` (quarter-kelly allocation percentage, 0.0% to 8.0%, or up to 10.0% half-Kelly on exceptional $\ge 5.0\times$ asymmetry)
- `passing_discipline_checks: dict[str, str]` (evaluation against commodity peaks, excessive debt, illiquidity)
- `cio_deliberation_summary: str` (executive committee statement)
- `upside_anchor: float | None`
- `upside_anchor_source: str`
- `bear_anchor_source: str`
- `paper_trade: bool`
- `bear_floor: float | None`

### `run_investment_committee(state: InvestigationState, model: Any) -> dict[str, Any]`
- **Input**: `InvestigationState` with facts, market context, consensus snapshot, and adversarial report.
- **Process**:
  1. Check Pre-Trade Gates: 20d ADDV $\ge \$5\text{M}$ and Earnings Proximity $\ne \text{"BLACKOUT\_RISK"}$.
  2. Compute 3:1 Asymmetry ratio against deterministic upside and bear downside anchors.
  3. Compute Fractional Kelly size via `compute_fractional_kelly`.
  4. Prompt model under CIO persona (`cio-ic.prompt.md` standard) to deliberate on conviction.
- **Output**: Dictionary updating `state["ic_verdict"]`.

### `MacroDirective`
- `monetary_regime: str` (`"ACCOMMODATIVE_EASING"`, `"NEUTRAL_TRANSITION"`, `"RESTRICTIVE_TIGHTENING"`)
- `yield_curve_regime: str` (`"BULL_STEEPENING"`, `"FLAT_NORMALIZATION"`, `"INVERTED_RECESSION_SIGNAL"`)
- `fed_funds_rate: float | None`
- `treasury_10y_yield: float | None`
- `yield_spread_10y_2y: float | None`
- `favored_sectors: list[str]`
- `unfavored_sectors: list[str]`
- `cio_macro_summary: str`
- `status: Literal["available", "insufficient_data"]`

### `run_macro_investment_committee(state: InvestigationState, model: Any) -> dict[str, Any]`
- **Input**: `InvestigationState` with macroeconomic series from FRED (`FEDFUNDS`, `DGS10`, `T10Y2Y`, `CPIAUCSL`, `UNRATE`).
- **Process**:
  1. Deterministically classify monetary policy regime based on `FEDFUNDS` rate.
  2. Deterministically classify yield curve geometry based on `T10Y2Y` slope.
  3. Prompt CIO model to author strategic sector overweight/underweight tilts.
- **Output**: Dictionary updating `state["macro_directive"]`.

## Donor Code Provenance

| Local symbol | Reuse type | Exact donor location | Deliberate changes |
| --- | --- | --- | --- |
| `app.agent.committee.CIO_SYSTEM_PROMPT` | adapted | `reference/investment-research/prompts/cio-ic.prompt.md:1-40` | Adapted into single CIO deliberation prompt enforcing 3:1 asymmetry, passing discipline, and position sizing. |
| `app.agent.committee.ICVerdict` | adapted | `reference/investment-research/schemas/ic-verdict.schema.json` | Python frozen dataclass for the formal investment committee verdict. |

## Acceptance Criteria
1. Any stock failing 20d ADDV ($< \$5\text{M}$) or earnings blackout ($\le 7$ days) is immediately assigned `PASSED_STRICT_DISCIPLINE` with `0.0%` allocation.
2. 3:1 Asymmetry Hurdle is mathematically evaluated: $(\text{Upside} / \text{Downside}) \ge 3.0$.
3. Quarter-Kelly position size is bounded between 0.0% and 8.0%.
