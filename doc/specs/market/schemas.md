# Module Spec — `app/market/schemas.py`

## Responsibility

Immutable validated records for market context. No network, no pandas, no yfinance imports.

## Public contracts

### `Quote`
`price`, `previous_close`, `change`, `change_percent`, `volume`, `currency`, `exchange`, `as_of` (ISO UTC). Price/previous_close/volume are floats/ints or None; `price` must be present for a usable quote. Validation raises `ValueError` on negative volume or unknown None/str types.

### `CalculatedField`
`value: float | None`, `lookback: str` (e.g. `"1d"`, `"20d-vol"`, `"sma-50"`), `benchmark: str | None`, `status: Literal["ok","unavailable"]`, `provider: str`, `as_of: str`. `status="ok"` requires `value is not None`.

### `MarketDataResult`
- `ticker` uppercase, `period` string, `quote: Quote | None`.
- `returns`: dict with keys `1d`,`5d`,`1m`,`3m` -> `CalculatedField`.
- `volume_ratio_20d`, `atr_14`, `benchmark_return`: `CalculatedField` (benchmark_return declares `benchmark`).
- `sma_50_status`, `sma_200_status`: `Literal["above","below","unavailable"]`.
- `market_cap`, `shares_outstanding`, `short_interest`: float | None with `reliable: bool` companion semantics — represented as `dict | None` `fundamentals` with keys `market_cap`, `shares_outstanding`, `short_interest_pct`, each `{"value": x|None, "reliable": bool}`.
- `provider`, `as_of`. `to_dict()`/`from_dict()` round trip re-validating.

### `MarketDataError`
`Exception` subclass: `provider`, `message`, `recoverable=True`.

## Constraints
Standard library only. Named constants for allowed keys. Docstrings on public methods.

## Donor code provenance
No donor code copied; local contracts.

## Tests
`tests/market/test_schemas.py` — validation, frozen, round trip, ok-status/requires-value rule.
