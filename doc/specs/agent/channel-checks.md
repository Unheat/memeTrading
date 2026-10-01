# Module Spec — Scuttlebutt Channel Check & Expectation Arbitrage Upgrades

## Goal

Upgrade the research engine from a rear-view SEC-only forensic accountant into an institutional
buyside pipeline that systematically collects **ground-truth channel telemetry** (Philip Fisher
Scuttlebutt / modern channel checks), stores it as auditable receipts, and folds it into a
**3-way Expectation Arbitrage synthesis** (Channel telemetry vs. Market pricing vs. SEC execution)
without weakening the deterministic citation and evidence-integrity gates.

## Institutional background (from research)

- Point72 (Canvas): value-chain concordance grids — count independent confirmations vs contradictions.
- Coatue: developer & infrastructure telemetry (GitHub velocity, operator forums) months before contracts.
- YipitData: transaction-to-KPI calibration against reported revenue (<2% variance).
- Woozle: falsifiable channel questions per thesis.
- Hedge funds reject vague sentiment scores (0.65 bullish) because they cannot be mapped to
  EPS/FCF, are noisy, and are not auditable. Every observation must be a **structured receipt**.

## Requirements

### R1 — Structured channel-check receipts (contracts)
`app/agent/contracts.py` gains:

- `ChannelCheckReceipt(BaseModel)`:
  - `receipt_id: str` (unique per observation)
  - `channel_type: Literal["distributor_inventory", "spot_pricing", "developer_telemetry",
    "sysadmin_operator_feedback", "merchant_adoption", "customer_churn", "retail_shelf_check"]`
  - `source_url_or_channel: str`
  - `target_ticker: str` (uppercased)
  - `observed_metric: str`, `observed_value: float | str`
  - `baseline_value: float | str | None = None`
  - `implication: Literal["bullish_inflection", "neutral", "bearish_inflection"]`
  - `quote_or_evidence: str` (verbatim excerpt)
  - `observed_at_utc: str` (ISO timestamp)
  - `to_dict()` serializer matching BullCase/BearCase convention.
- `ChannelCheckReport(BaseModel)`:
  - `ticker: str`, `status: Literal["available", "insufficient_data", "degraded"] = "insufficient_data"`
  - `receipts: list[dict]` (serialized receipts)
  - `receipts_count: int`, `bullish_count: int`, `bearish_count: int`, `discordant_signals: int`
  - `channel_implied_growth: float | None = None` (deterministic proxy only — see R3)
  - `channel_verdict: Literal["CHANNEL_ACCELERATION", "CHANNEL_BREAKDOWN", "MIXED_CHANNEL", "INSUFFICIENT_CHANNEL_DATA"]`
  - `synthesis_summary: str = ""`
  - `to_dict()` serializer.

### R2 — Planner mandate for channel-check evidence (planning)
`app/agent/planning.py`:

- `ResearchHypothesis.evidence_tier` gains `"channel_check_primary"` in its Literal.
- `generate_research_plan` system prompt instructions describe the new tier and direct the
  planner to emit at least one `channel_check_primary` hypothesis for tech / semiconductor /
  software / consumer candidates (distributor stockouts, spot prices, developer telemetry,
  operator feedback, churn chatter).
- No regex/keyword intent inference: the mandate lives in the structured planner prompt only.

### R3 — Channel-check specialist (specialists + diligence)
`app/agent/specialists.py` gains `run_channel_check_analysis(state, model=None)`:

- Deterministic base path (model=None or model failure):
  - Aggregates social/tool evidence already present in the candidate workspace
    (`evidence` items, `capability_outputs.social_signal` when present).
  - Classifies each observation's implication from explicit fields when present
    (`implication`, `velocity_24h`, `trend`); unknown signals count as neutral.
  - Produces `channel_check_report` with counts, verdict, and honest `status`
    (`insufficient_data` when fewer than 2 observations).
- Model path: prompts the model with the deterministic receipt JSON to author only the
  `synthesis_summary`; all counts/verdict remain deterministic.
- Verdict rule (deterministic): bullish_count >= 2 and bullish > bearish →
  `CHANNEL_ACCELERATION`; bearish_count >= 2 and bearish > bullish → `CHANNEL_BREAKDOWN`;
  >= 2 observations otherwise → `MIXED_CHANNEL`; else `INSUFFICIENT_CHANNEL_DATA`.
- `channel_implied_growth` is **not invented**: it stays None unless a deterministic upstream
  metric exists (future YipitData-style calibration); the report keeps the slot for it.

`app/agent/diligence.py` `run_candidate_diligence`:

- Runs `run_channel_check_analysis` in the Stage-1 parallel pool (4 workers now) alongside
  expectations, forensic, and moat; result merges into the candidate state as
  `channel_check_report` and lands in the dossier via `build_diligence_dossier`.

### R4 — 3-way expectation arbitrage (expectations + memo)
`app/agent/expectations.py`:

- `run_expectations_analyst` reads `channel_check_report` from candidate state
  (`channel_implied_growth` when deterministically available).
- `ExpectationGapAnalysis` gains `channel_growth_estimate`, `arbitrage_delta`
  (= channel − max(implied, consensus) when both sides exist), and
  `arbitrage_verdict` with deterministic classification:
  - `UNPRICED_CHANNEL_ACCELERATION` (delta > +5pp), `CHANNEL_BREAKDOWN_SHORT`
    (delta < −5pp with high implied), `PRICED_TO_PERFECTION` (implied > 25% and channel
    not confirming), else `CONSENSUS_ALIGNED` / `UNCERTAIN_DISPERSION` when inputs missing.
  - Reuses `EXPECTATION_GAP_PRICED_IN_MARGIN` for the ±5pp threshold.
- `to_dict()` serializes the three new fields.

`app/agent/memo.py`:

- `_expectations_section` renders a new **Expectation Arbitrage (3-Pillar)** block when a
  `channel_check_report` exists in state: pillar table (Ground telemetry | Market pricing |
  SEC execution | Expectation edge), plus the channel verdict line. When no channel report
  exists the section renders exactly as before (no regression).

### R5 — State wiring
`app/agent/state.py`:

- `InvestigationState` gains `channel_check_report: dict[str, Any] | None`.
- `create_initial_state` initializes it to `None`.

### R6 — Honest degradation
- All new code paths degrade gracefully: model failure → deterministic counts only;
  no channel data → `INSUFFICIENT_CHANNEL_DATA` with `status="insufficient_data"`.
- No new LLM-arithmetic: numeric fields come from deterministic classification only.

## Acceptance criteria

1. `ChannelCheckReceipt` and `ChannelCheckReport` validate via Pydantic and serialize via
   `to_dict()`; invalid `channel_type`/`implication` values are rejected.
2. `ResearchHypothesis(evidence_tier="channel_check_primary")` validates; the planner prompt
   documents the tier.
3. `run_channel_check_analysis` with zero observations returns
   `INSUFFICIENT_CHANNEL_DATA` / `insufficient_data`; with 2+ bullish observations returns
   `CHANNEL_ACCELERATION`; bearish-heavy returns `CHANNEL_BREAKDOWN`; mixed returns
   `MIXED_CHANNEL`. Model narrative failure still yields the deterministic report.
4. Diligence dossiers include `channel_check_report`.
5. `run_expectations_analyst` computes `arbitrage_delta` deterministically when channel and
   implied/consensus data exist, and classifies the four verdicts; without channel data the
   output matches the previous behavior (regression-safe).
6. Memo renders the 3-pillar arbitrage table only when a channel report exists.
7. Full test suite passes (`pytest tests/`).

## Donor code provenance

No donor code is copied for these modules; all channel-check logic is locally written.
The 3-pillar arbitration concept follows Mauboussin expectations investing already present in
`app/agent/expectations.py` (donor: `reference/investment-research/prompts/valuation-modeler.prompt.md`).
