# Execution Plan 12 — Company Research & Expectations Framework (Phase A)

## Purpose

Implement the `get_company_research` outer-agent tool specified in `doc/fullplan.md` (nine tools) and upgrade the agent prompt and forensic memo with the Scuttlebutt & Expectations methodology: Fisher/Lynch ground-reality tracing, management-execution audit, and the Mauboussin expectation-gap benchmark against Wall Street consensus.

## Boundaries

- `get_company_research` is secondary research data for the expectation-gap comparison, never authoritative proof and never a recommendation.
- yfinance first (keyless); Finnhub optional later (Phase B) when `FINNHUB_API_KEY` exists.
- Companies without institutional coverage return explicit per-field `unavailable` status, never zeros.
- Tests are deterministic and offline: mocked yfinance seams, no network.

## Donor code provenance

| Local symbol | Reuse type | Exact donor location | Deliberate changes |
| --- | --- | --- | --- |
| `app.market.company_research` | black-box dependency | `ranaroussi/yfinance` public API (`Ticker.analyst_price_targets`, `Ticker.recommendations`, `Ticker.earnings_estimate`, `Ticker.revenue_estimate`, `Ticker.calendar`) | No donor code copied; wrapped behind testable seams with per-section degradation and provenance stamps. |
| `app.agent.prompts` lenses | adapted | `reference/ai-hedge-fund/hedge_fund/signals/{druckenmiller,lynch,buffett}.py` (lens concepts only, per fullplan policy) | Synthesized into single charter prompt; no persona agents. |
| `app.agent.memo` formats | adapted | `reference/financial-research-workshop/agents/deep_agent/skills/investor-note/SKILL.md` and `earnings-summary/SKILL.md` | Deterministic rendering from state; unknown values rendered `n/a`. |

## Required behavior

1. **`app/market/company_research.py`**
   - `ConsensusValue(value, status, provider, as_of)` — `status="ok"` requires value.
   - `PriceTargets(low, mean, high)` of ConsensusValue.
   - `RatingsSnapshot(buy, hold, sell, strong_buy, strong_sell, total, status, provider, as_of)`.
   - `EstimateRow(metric, period, avg, low, high, n_analysts, growth, provider, as_of)`.
   - `CompanyResearchResult(ticker, price_targets, ratings, eps_estimates, revenue_estimates, next_earnings_date, provider, as_of)` with `to_dict()`/`from_dict()`.
   - `get_company_research(ticker) -> CompanyResearchResult`: validates ticker; fetches price targets, ratings, EPS/revenue estimates, calendar via four yfinance seams; each section degrades independently on failure; missing coverage -> `unavailable` status / None.

2. **Tool registry (`app/agent/tools.py`)** — add 9th tool `get_company_research` with duplicate guard and JSON serialization.

3. **State (`app/agent/state.py`)** — add `consensus_snapshot: dict | None` and `expectation_gap: dict | None` to `InvestigationState` + `create_initial_state`.

4. **Prompt (`app/agent/prompts.py`)** — add the three lenses: scuttlebutt beneficiary tracing, management-execution audit (margins/inventory/CapEx/financing from XBRL via edgartools), expectation-gap benchmark via `get_company_research`.

5. **Memo (`app/agent/memo.py`)**
   - Investor-note opening: headline (<= 15 words from trigger), bottom line (first two sentences of synthesis), drivers (root claims), risks/what-we-are-watching (thesis breakers, else unresolved questions).
   - `## Wall Street Expectations vs Ground Reality` section: consensus variance table (metric, consensus, revision/growth) in `earnings-summary` format plus expectation-gap verdict from `expectation_gap` state; renders only when consensus data present; otherwise explicit note that no institutional coverage exists.

## Execution steps

1. Write spec `doc/specs/market/company_research.md`.
2. Red tests `tests/market/test_company_research.py` -> implement -> green.
3. Register tool + state fields; update `tests/agent/test_tools.py` expected set to nine tools.
4. Upgrade prompt + memo; extend `tests/agent/test_memo.py` and `tests/agent/test_state.py`.
5. Full suite green; commit Phase A.
