# Execution Plan 02 — SEC Filing Discovery

## Purpose

Implement metadata-only SEC filing discovery behind the future `list_sec_filings` outer-agent tool. This slice converts an explicitly requested ticker, form set, and optional date bound into normalized `FilingMetadata` records. It must not download filing bodies or build a corpus.

## Boundaries

- Use `edgartools` as a library black box; do not copy its SEC transport or parsing code.
- No filing or exhibit download, local document write, corpus creation, RAG, verifier, outer agent, API, UI, or database.
- No autonomous ticker selection. Caller supplies ticker.
- Production code is allowed to access SEC data through Edgartools; unit tests must use fakes/mocks and make no network calls.
- Preserve SEC source URLs and receipt fields needed by the completed foundation contracts.

## Required behavior

`list_sec_filings(ticker, forms=None, since=None)` must:

1. Normalize and validate ticker through the existing contract rules.
2. Resolve company and CIK through Edgartools.
3. Request filing metadata only.
4. Filter by requested form values and inclusive `since` date when provided.
5. Map each selected source filing to `FilingMetadata`.
6. Return records in newest-first deterministic order.
7. Include discoverable primary-document and exhibit names only when metadata exposes them cheaply; never fetch an attachment to discover it.
8. Return a structured, recoverable result for unknown tickers, invalid caller input, unavailable SEC data, or malformed upstream metadata. It must not leak raw Edgartools exceptions to the future agent tool boundary.

## Files expected during implementation

```text
app/sec/acquisition.py
tests/sec/test_acquisition.py
doc/specs/02-sec-filing-discovery.md
```

If dependency declaration becomes necessary, add the smallest normal project dependency configuration rather than importing code from `reference/edgartools` by filesystem path.

## Execution steps

1. Inspect the current installed Edgartools public API and the donor’s `Company`/filings behavior. Confirm exact version and supported metadata fields before writing the module spec. If behavior is uncertain, consult official Edgartools documentation rather than guessing.
2. Write `doc/specs/02-sec-filing-discovery.md` immediately before production code. Define public result/error types, input normalization, form/date filtering, ordering, and upstream-to-`FilingMetadata` mapping.
3. Create red tests using fake company/filing objects. Cover normal listing, omitted filters, form filter, inclusive `since`, sort order, invalid ticker/date, unknown company, upstream outage, and incomplete metadata.
4. Run targeted tests. Record expected red failure before creating production module.
5. Implement the smallest Edgartools adapter in `app/sec/acquisition.py`.
6. Run targeted tests until green. Do not make live SEC requests in the normal test suite.
7. Add one separately marked/manual smoke check only if SEC identity configuration and network access are available; it must not run by default.
8. Run all local tests and compile application code.
9. Update this plan and module spec with actual behavior, version assumptions, and test results.

## Donor/reference boundary

Use only public Edgartools behavior represented by:

- `reference/edgartools/edgar/entity/core.py` — `Company` entry point and filing access.
- `reference/edgartools/edgar/entity/filings.py` — filing collection behavior, only after public API inspection confirms relevance.

Do not port either file. This application owns the thin adapter and output contract.

## Done checkpoint

This slice is complete when a caller can obtain validated, deterministic filing metadata without document downloading; all expected provider failures are recoverable; automated tests are network-free; and no code outside the listed acquisition slice changes. Next slice is controlled filing/exhibit pull into `PulledCorpus`.

## Execution record

Completed on 2026-09-01. Edgartools 5.55.0 donor public API was inspected: `Company(ticker).get_filings(form=..., trigger_full_load=False)` provides metadata-only filing enumeration. The adapter uses only metadata fields and never accesses document or attachment properties. Red tests initially failed because `app.sec.acquisition` did not exist. A local form-filter defect was caught and fixed; final verification passed with 16 tests. Live smoke check deferred because Edgartools and SEC identity configuration are not installed locally.
