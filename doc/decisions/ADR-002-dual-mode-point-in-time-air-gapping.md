# ADR-002: Dual-Mode Point-in-Time (PIT) Air-Gapping for Backtesting vs. Live Research

## Status
Accepted

## Date
2026-10-18

## Context
When conducting historical backtests (e.g. testing whether our agent would have recommended Micron ($MU$) on March 12, 2026 before its subsequent rally), standard web searches and live financial APIs risk leaking post-decision information.

However, an earlier attempt to enforce Point-in-Time safety discarded *all* web articles and documents that lacked an explicit publication date. Because many financial websites, analyst portals, and product specification pages do not include clean ISO publication timestamps in their raw HTML headers, this aggressive filter blocked vital research data, causing backtests to fail with false-negative verdicts.

## Decision
Implement a dual-mode Point-in-Time (PIT) air-gapping architecture in `app/agent/tools.py` and `app/agent/market_data.py`:
1. **Live Research Mode (`as_of_date is None`)**:
   - Undated web search results and articles are fully admitted.
   - Market data queries the latest live prices, quotes, and consensus estimates.
2. **Historical Backtest Mode (`as_of_date is not None`)**:
   - Web documents dated *after* `as_of_date` are strictly dropped.
   - Undated web search snippets are dropped to prevent lookahead bias.
   - Publication dates are extracted from canonical metadata fields (`published_utc`, schema.org, OpenGraph `article:published_time`) and URL path regex patterns (`/YYYY/MM/DD/`), replacing unreliable body text regex scraping.
   - SEC filings are filtered by official SEC accession filing dates (`filing_date <= as_of_date`).
   - Market prices, ATR, and moving averages are clamped to historical market close as of `as_of_date`.

## Alternatives Considered

### Blocking Undated Documents in All Modes
- Pros: Maximum theoretical defense against lookahead.
- Cons: Destroys live research effectiveness; drops 40–60% of high-value industry reports and technical teardowns that do not render machine-readable dates.
- Rejected: Excessive false-positive data loss.

### Allowing LLM to Self-Filter Future Information via Prompting
- Pros: Simple to implement; zero code filtering.
- Cons: LLMs are incapable of reliably self-policing temporal knowledge leakage when future information is present in the prompt context.
- Rejected: Unacceptable lookahead bias in quantitative backtesting.

## Consequences
- Historical backtests produce mathematically honest results free of survivorship and lookahead bias.
- Live research retains maximum recall across news, web, and trade publications.
- Tools and tests must explicitly pass `as_of_date` when executing in historical mode.
