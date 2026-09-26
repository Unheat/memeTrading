# Audit Fix Plan: Coherent Valuation & Governance Overhaul (v1)

Status tracking for the 2026-09-26 pipeline audit. Each batch executes on its own branch
from `main`, is verified against its acceptance criteria, then merges back to `main`.

**Goal**: One deterministic source of valuation truth; every model-authored claim validated
against deterministic evidence; the committee sees all specialist work; sizing calibrated
instead of binary.

**Constraints**: Outer tool contracts (`conduct_candidate_diligence` dossier schema,
`evaluate_valuation` output) stay identical; zero-TTS / media policies untouched; all fixes
tested.

---

## Batch A — Valuation Single-Source Truth (branch `fix/valuation-single-source-truth`)

### Fix 1: Growth assumptions silently discarded in capex-spike regimes
- **Problem**: `app/agent/specialists.py` hard-codes `fcf_trajectory = [fcf×1.05, ×1.15, ×1.25, ×1.30, ×1.35]`
  when CapEx/revenue > 25%; `app/valuation/calculator.mjs` `dcf()` uses a provided trajectory
  *instead of* the case growth rate.
- **Impact**: For AI-capex names (the core use case) the expectations analyst's authored
  growth (recorded in the report) is never applied; low/base/high collapse into one fixed
  ladder shape. Verified on GOOG: flows matched the ladder to the cent.
- **Fix**: Stop auto-generating the fixed ladder. Let `dcf()` apply `fcfBase * (1+g)^y`
  directly (two-stage DCF). Regime detection only decides `fcf_base` normalization
  (maintenance-CapEx), not the shape of the future. The explicit trajectory parameter stays
  for genuinely analyst-supplied schedules.
- **Accept**: property test — fair value strictly monotonic in case growth rate.

### Fix 2: `evaluate_valuation` computes a second, amnesiac valuation
- **Problem**: `app/agent/tools.py` builds a fresh state without `expectation_gap`
  (fallback 5% growth) or `macro_context` (FRED DGS10 → static 4.30% rf default).
  Two unreconciled DCFs enter the record (GOOG: $306.41 dossier vs $254.56 gate).
- **Impact**: The more conservative valuation wins by accident; dynamic-WACC feature
  silently off in this path; 20% divergence larger than the decision edge.
- **Fix**: (a) inject current state via LangGraph `InjectedState`; inherit
  `expectation_gap` + `macro_series` when present; fetch FRED DGS10 when absent.
  (b) Input-hash memoization: reuse the candidate's existing `quant_report` when inputs
  are unchanged (provenance `reused_diligence_quant`); reconcile and fail loudly when
  inputs match but outputs differ.
- **Accept**: with inherited assumptions, tool valuation == diligence-internal valuation
  for identical inputs; FRED fallback exercised in tests via stub.

### Fix 4: Beneish M-Score coefficients wrong
- **Problem**: `calculator.mjs` uses `+4.037·TATA` and `+0.0327·LVGI`; published 1999
  model is `+4.679·TATA − 0.327·LVGI` (sign + decimal wrong on LVGI).
- **Impact**: ~0.30–0.36 systematic score inflation → false-positive manipulation flags
  near the −1.78 threshold.
- **Fix**: correct coefficients; regression test with hand-computed published-coefficient
  value + directional tests (higher LVGI must lower the score).
- **Accept**: worked-example test passes; GOOG-class profile stays clean.

### Fix 8: Vacuous reproducibility verification
- **Problem**: `calculator.mjs` `verify()` compares `fair_value_per_share` from the input
  model, which never carries stored values — mismatch branch unreachable. Slim tool view
  reads `.verdict` at the wrong nesting → reports "unverified" while underlying says "pass".
- **Fix**: inject computed results into the verify model before the second run; require
  ≥1 actual comparison (else `inconclusive`); normalize `reproducibility` shape to
  `{verdict, mismatches, compared_cases}` and fix consumers.
- **Accept**: a deliberately corrupted stored value produces verdict `fail`; unmodified
  replay produces `pass` with `compared_cases >= 1`.

## Batch B — Honest Structured Outputs (branch `fix/structured-output-validation`)

### Fix 3: Reverse-DCF narrative numbers fabricated against deterministic evidence
- **Problem**: `app/agent/expectations.py` — `verdict` / `summary` /
  `implied_growth_interpretation` are raw LLM text. Deterministic prelim: 8.86% @ 9.0%;
  recorded: "20.38% @ 9.0%" — repeated in the article as fact.
- **Fix**: `implied_fcf_growth_rate` becomes a deterministic field (from the calculator
  prelim only). `implied_growth_interpretation` becomes a deterministic template embedding
  the real number; LLM commentary moves to a qualitative field. `verdict` becomes a
  deterministic classification (implied growth vs consensus growth spread, named
  thresholds). Numeric-claim validator downgrades to `degraded` + deterministic template
  on contradiction (verification, not intent inference).
- **Accept**: unit tests — fabricated number replaced; verdict deterministic; schema unchanged
  externally except added fields.

### Fix 6: One-sided debate — bull numeric anchor optional and unvalidated
- **Problem**: red team always supplies `bear_floor_price`; bull returned
  `bull_target_price: null` with no validation/retry; committee ratio swung 0.56 → 3.14
  (approval) on this field alone.
- **Fix**: structured retry (one round) with validation error fed back; if still missing,
  report flagged `degraded`; committee falls back to consensus-high target with explicit
  `upside_anchor_source: "consensus_high_fallback"`; symmetric `bear_anchor_source` fallback
  to DCF low. Both sources surfaced in the CIO payload and ICVerdict.
- **Accept**: retry test; fallback-marking test; anchors/sources visible in payload.

### Fix 7: Silent degradation with dishonest status flags
- **Problem**: moat claims `status: "available"` after total LLM failure; one malformed
  field (`bear_floor: "abc"`) discards the entire bear report.
- **Fix**: field-level parsing; status vocabulary `{available, degraded, unavailable}`;
  `degraded` mandatory when any fallback fired; `degradation_reasons[]` recorded.
- **Accept**: malformed-input probe shows `degraded`, never fake `available`.

### Fix 10: CIO prose can mislabel the upside anchor
- **Problem**: payload key `base_target_price` holds `max(consensus, DCF, bull)` — CIO
  called the Street's $422.34 mean "our base DCF".
- **Fix**: rename payload fields (`upside_anchor`, `upside_anchor_source`,
  `dcf_base_fair_value`); CIO schema gains required `anchor_citation`.
- **Accept**: payload shows both DCF and anchor separately; CIO output carries citation.

## Batch C — Completeness & Hygiene (branch `fix/moat-and-reflection-completeness`)

### Fix 5: Moat analysis discarded before deliberation
- **Problem**: dossier reduces moat to `moat_rating`; graph unpacks every other specialist
  except moat; CIO payload has no moat field.
- **Fix**: dossier carries `moat_report`; graph unpacks to state; CIO payload gains
  `moat: {rating, durability}`.
- **Accept**: re-run GOOG case → CIO payload contains the moat block.

### Fix 9: Reflection gap injector flags any `.pdf` URL
- **Problem**: `graph.py` — no domain/relevance filter; run demanded FASAB /
  comptroller.war.gov PDFs.
- **Fix**: only flag issuer-relevant PDFs (SEC.gov or candidate-correlated source records);
  cap 1 per round.
- **Accept**: junk-domain PDF test filtered; sec.gov PDF still flagged.

### Hardening
- `ToolCallGuard.check_and_record` coerces signatures to hashable internally (latent
  `TypeError` on raw dict).
- Kelly parity test: JS and Python implementations must agree on `f*` for identical inputs.

## Batch D — Profitability Architecture (branch `feat/tiered-sizing-and-backtest`)

Honest framing: code fixes make the model *correct*; only measurement makes profitability
claims honest. This batch makes the system calibratable and aggressive when evidence
supports it.

1. **Tiered allocation**: ratio ≥ 3.0 → quarter-Kelly (current); ≥ 5.0 with no degraded
   reports → half-Kelly; 2.0–3.0 → paper-trade queue (decision recorded, zero capital,
   `paper_trade: true` in verdict).
2. **Configurable asymmetry hurdle** per mandate style (`research.asymmetry_hurdle`,
   profiles `deep_value=3.0` / `compounder=2.0` / `momo=4.0`).
3. **Deterministic expectation-edge signal**: `consensus_growth − implied_growth` as a
   first-class ranking metric in `compare_candidates`.
4. **Decision ledger + backtest harness** (`tools/backtest_score.py`): score historical
   cases vs forward 3/6/12-month returns (price provider injectable for tests) — hit rate,
   realized vs predicted reward:risk, win-prob calibration.
- **Accept**: tiered sizing unit tests; config profiles parse; backtest scorer works on
  synthetic cases with injected prices.

---

## Execution log

- [x] Feature branch `feat/concurrent-diligence-and-tool-batching` merged to main (e2e validated)
- [x] Batch A merged — `fix/valuation-single-source-truth` (Fixes 1, 2, 4, 8; 12 tests)
- [x] Batch B merged — `fix/structured-output-validation` (Fixes 3, 6, 7, 10; 11 tests)
- [x] Batch C merged — `fix/moat-and-reflection-completeness` (Fixes 5, 9 + hardening; 6 tests)
- [x] Batch D merged — `feat/tiered-sizing-and-backtest` (P2 profitability architecture; 8 tests)
- [x] Final GOOG e2e re-run comparison — see "Post-fix e2e results" below
