# Module Spec — `app/sec/acquisition.py`

## Status

Complete on 2026-09-01. Red phase failed during collection with `ModuleNotFoundError: No module named 'app.sec.acquisition'`. Green verification: 16 local tests passed and application compilation completed. Edgartools is declared in `requirements.txt` but intentionally not installed in this workspace; no live SEC smoke check was run.

## Responsibility

Expose metadata-only filing discovery for one caller-supplied ticker. It adapts Edgartools 5.55.x public `Company(ticker).get_filings(...)` output into `FilingMetadata` without downloading any filing, primary document, or exhibit.

## Dependency boundary

`edgartools>=5.55,<6` is a runtime dependency. Production imports it lazily only when the default company factory is used. Tests inject a fake factory and never import Edgartools or access network services.

The adapter may read only filing metadata fields: `form`, `filing_date`, `accession_no` or `accession_number`, `url` or `homepage_url`, and company `cik`. It must not access `document`, `attachments`, `exhibits`, `homepage`, `html`, `text`, or download methods.

## Donor code provenance

No donor implementation was copied or adapted into this module. `list_sec_filings` is local adapter code. It uses Edgartools as a black-box dependency through the public metadata-enumeration behavior inspected at `reference/edgartools/edgar/_filings.py:1249-1368`, `get_filings`; that dependency use is not source reuse.

## Public contracts

### `DiscoveryError`

Fields: `code`, `message`, `retryable`. Error code is one of `INVALID_INPUT`, `NOT_FOUND`, `UNAVAILABLE`, `MALFORMED_UPSTREAM`, `DEPENDENCY_UNAVAILABLE`.

### `FilingDiscoveryResult`

Fields: `filings`, `error`. Successful result has non-null tuple `filings` sorted by filing date descending then accession descending, and `error=None`. Failed result has `filings=()` and one `DiscoveryError`.

### `list_sec_filings(ticker, forms=None, since=None, company_factory=None)`

Inputs:

- `ticker`: 1–10 alphabetic characters, normalized to uppercase.
- `forms`: optional non-empty iterable of form strings. Normalized to uppercase; empty list means no form filter.
- `since`: optional `date` or JSON-native ISO `YYYY-MM-DD` string; filing date is included when equal or later.
- `company_factory`: optional test seam accepting normalized ticker and returning a company-like object.

Output: `FilingDiscoveryResult`; expected upstream and input failures are never raised to callers.

Behavior:

1. Validate inputs before creating a company.
2. Resolve company and call `get_filings(form=normalized_forms_or_none, trigger_full_load=False)`.
3. Map only complete metadata to `FilingMetadata`; `primary_document=None`, `exhibits=()` in this discovery-only slice.
4. Apply an inclusive local `since` filter and deterministic sort.
5. Treat an empty upstream list as successful empty discovery.
6. Translate missing company/CIK to `NOT_FOUND`; import failure to `DEPENDENCY_UNAVAILABLE`; expected provider transport errors to retryable `UNAVAILABLE`; incomplete or invalid upstream records to retryable `MALFORMED_UPSTREAM`.

## Constraints

- No filesystem write, corpus creation, filing download, RAG, LLM, API route, or agent import.
- No live network test or default smoke test.
- Public classes/functions have purpose/input/output/failure docstrings.

## Test cases

`tests/sec/test_acquisition.py` must cover normal listing, omitted form filter, normalized form filter, inclusive date filtering for direct `date` and model-facing ISO strings, malformed date rejection, newest-first ordering, invalid ticker, missing company CIK, unavailable provider, incomplete filing metadata, and proof that fake filings expose no document-download behavior.
