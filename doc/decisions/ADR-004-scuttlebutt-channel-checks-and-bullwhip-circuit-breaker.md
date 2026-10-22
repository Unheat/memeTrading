# ADR-004: Scuttlebutt Channel Checks & Bullwhip Circuit Breaker

## Status
Accepted

## Date
2026-10-18

## Context
Standard equity research relies heavily on backward-looking SEC filings (10-K and 10-Q), which report financial performance with a 45–90 day lag. In rapidly inflecting industries (e.g. semiconductor memory shortages, AI accelerator packaging bottlenecks), by the time an inflection appears in official filings, the stock has already rallied significantly.

Conversely, relying on raw social media hype or distributor rumors exposes models to false positives, spam campaigns, and "bullwhip" phantom inventory hoarding where customers over-order during perceived shortages.

## Decision
Implement a structured Scuttlebutt Channel Check framework (Philip Fisher methodology) governed by the SEC Mosaic Theory and mathematical risk controls:
1. **Auditable `ChannelCheckReceipt` Ledger**:
   - Field evidence is broken into individually non-material, publicly observable facts (`receipt_id`, `channel_type`, `observed_metric`, `observed_value`, `source_url_or_channel`, `quote_or_evidence`).
   - Every receipt is assigned a Source Tier (`tier_1_physical_core` 1.0, `tier_2_distribution` 0.6, `tier_3_developer` 0.3, `tier_4_public` 0.05) and an Observation Grade (`grade_a_hard_metric` 1.0, `grade_b_action` 0.7, `grade_c_soft` 0.3, `grade_d_rumor` 0.05).
   - Vague sentiment and social chatter are mathematically downweighted (a viral Reddit thread has an effective weight of $0.05 \times 0.05 = 0.0025$, requiring 400 posts to match one verified supplier quote).
2. **Scuttlebutt Inflection Exception**:
   - When channel telemetry confirms `CHANNEL_ACCELERATION` (e.g., 3:1 wafer cannibalization, lead times > 26 weeks, distributor inventories collapsed to 4–5 weeks), upside is unblocked to the high operating leverage target (`quant_high_channel_acceleration`) and downside is anchored to dynamic ATR volatility support.
3. **The Bullwhip Phantom Inventory Circuit Breaker**:
   - Before approving `CHANNEL_ACCELERATION`, the channel specialist executes a hard accounting check:
     If Days Inventory Outstanding ($\text{DIO} > 135\text{ days}$) and inventory expands $>15\%$ QoQ on the audited balance sheet, the verdict is overridden to `SUSPECTED_PHANTOM_INVENTORY_HOARDING`, preventing the firm from buying into cyclical over-ordering traps.

## Alternatives Considered

### Relying Solely on Backward-Looking SEC Disclosures
- Pros: Maximum auditability.
- Cons: Misses structural inflection points; repeatedly passes on winning trades during the early phases of supercycles (as observed in the Micron March 2026 backtest).
- Rejected: Ineffective for alpha generation.

### Unconstrained LLM Sentiment Scoring on Social Feeds
- Pros: High responsiveness to buzz.
- Cons: Extreme vulnerability to bot swarms, coordinated pump-and-dump campaigns, and hallucinated retail narratives.
- Rejected: Violates institutional capital preservation rules.

## Consequences
- The research pipeline captures real-world supply/demand inflections months ahead of SEC filings.
- Retail social noise is mathematically contained.
- False supercycles are filtered out by the bullwhip balance sheet check.
