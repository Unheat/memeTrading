# Module Spec — `app/storage/cases.py`

## Status

Complete on 2026-09-01. Initial red tests failed because the `app` package did not exist. Green verification completed with the local suite passing.

## Responsibility

Safely create deterministic case identifiers and persist/load one validated `PulledCorpus` manifest in local case storage. This module performs no SEC, web, social, market, retrieval, or LLM request.

## Public contracts

### `StorageError`

Domain exception raised when a corpus manifest is missing, malformed JSON, or violates schema validation. Callers should handle this instead of raw parser or key exceptions.

### `create_case_id(ticker, case_date, sequence)`

Input: alphabetic 1–10-character ticker, `date`, sequence 1–999.

Output: normalized `TICKER-YYYY-MM-DD-NNN` identifier.

Failure: invalid ticker or sequence raises `ValueError`.

### `case_path(cases_root, case_id)`

Input: configured cases root and a valid case ID.

Output: direct child path below `cases_root`. The function creates no directory.

Failure: invalid case ID or failed containment raises `ValueError`.

### `allocate_case(cases_root, ticker, case_date=None)`

Atomically creates a unique direct case directory by trying daily sequence IDs with `mkdir(exist_ok=False)`. It never reuses, deletes, or overwrites an existing case and raises `StorageError` after sequence exhaustion.

### `write_run_manifest(case_directory, manifest)` / `read_run_manifest(case_directory)`

Atomically persists and validates `run-manifest.json` in an existing case directory. A manifest records version, request snapshot, `running`/`completed`/`failed` lifecycle status, timestamps, stage, sanitized error, artifact inventory, and receipt summary. No database or network access occurs.

### `write_corpus_manifest(case_directory, corpus)`

Input: existing case directory and valid `PulledCorpus`.

Output: `case_directory/sec/corpus-manifest.json` path.

Behavior: creates only `sec/`, writes JSON through a sibling temporary file, and atomically replaces target. It does not make a network call.

Failure: missing case directory raises `ValueError`; filesystem write failures propagate as `OSError` after temporary-file cleanup.

### `read_corpus_manifest(case_directory)`

Input: case directory.

Output: validated `PulledCorpus` reconstructed from exactly `sec/corpus-manifest.json`.

Failure: absent path, malformed JSON, or invalid contract data raises `StorageError`. It does not make a network call.

## Constraints

- Standard library plus `app.sec.schemas` only.
- Case IDs cannot encode traversal.
- No database, cache, HTTP client, Edgartools, vector store, or LLM import.
- Public functions include purpose/input/output/failure docstrings.

## Donor code provenance

| Local symbol | Reuse type | Exact donor location | Deliberate changes |
| --- | --- | --- | --- |
| `app.storage.cases.write_run_manifest` and `read_run_manifest` | adapted | `reference/ai-financial-research-agent/app/api/schemas.py:13-19,64-84`, `reference/ai-financial-research-agent/app/api/service.py:81-94,163-198` | Compact local JSON lifecycle with atomic replacement; no FastAPI, database, threads, or events. |

All other symbols are local filesystem contracts. No donor code is copied for corpus storage or atomic allocation.

## Tests

`tests/storage/test_cases.py` covers deterministic IDs, direct-child paths without creation, manifest round trips, and corrupt-manifest errors. All tests use temporary local directories only.
