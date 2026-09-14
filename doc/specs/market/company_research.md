# Module Spec — `app/market/company_research.py`

## Responsibility

One Wall Street consensus benchmark tool for the expectation-gap comparison. Secondary research data with full provenance; never authoritative proof, never a recommendation.

## Public contracts

### `ConsensusValue`
`value: float | None`, `status: Literal["ok","unavailable"]`, `provider: str`, `as_of: str`. `status="ok"` requires `value is not None`.

### `PriceTargets`
`low`, `mean`, `high`: `ConsensusValue | None` each.

### `RatingsSnapshot`
`buy`, `hold`, `sell`, `strong_buy`, `strong_sell`, `total`: `int | None`; plus `status`, `provider`, `as_of`. Negative counts invalid.

### `EstimateRow`
`metric` (`"eps"` | `"revenue"`), `period` (yfinance label, e.g. `"0y"`, `"+1y"`), `avg`, `low`, `high`, `growth`: `float | None`; `n_analysts: int | None`; `provider`, `as_of`.

### `CompanyResearchResult`
`ticker` (uppercase), `price_targets: PriceTargets | None`, `ratings: RatingsSnapshot | None`, `eps_estimates: tuple[EstimateRow, ...]`, `revenue_estimates: tuple[EstimateRow, ...]`, `next_earnings_date: str | None`, `provider: str`, `as_of: str`. `to_dict()`/`from_dict()` round trip with validation re-applied. Empty coverage yields `None` sections and empty tuples — never fabricated values.

## Functions

- `get_company_research(ticker: str) -> CompanyResearchResult`
  - Validates uppercase alphanumeric ticker; raises `ValueError` on invalid.
  - Four yfinance seams (patch points): `_yf_price_targets`, `_yf_recommendations`, `_yf_estimates(metric)`, `_yf_calendar`. Each wrapped: exception or empty data degrades only that section.
  - `as_of` stamped once at call time; every ConsensusValue/Row/Snapshot carries provider + as_of.
  - Calendar dict handling: `Earnings Date` may be a list; first future-parseable value wins; unparseable -> None.

## Constraints

- No Finnhub import (Phase B adds it behind the same tool).
- No recommendation, target-price advice, or verdict in output.
- Standard library + existing market schemas only.

## Donor code provenance

Black-box dependency use of `ranaroussi/yfinance` public API; no donor code copied.

## Tests

`tests/market/test_company_research.py`: full-coverage mapping, empty-coverage degradation, per-section failure isolation, round trip, invalid ticker rejection.
