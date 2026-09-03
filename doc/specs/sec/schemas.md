# Module Spec — `app/sec/schemas.py`

## Status

Complete on 2026-09-01. Initial red tests failed because the `app` package did not exist. Green verification completed with the local suite passing.

## Responsibility

Define immutable, validated, JSON-round-trippable records shared by future SEC discovery, downloading, case corpus indexing, and local verification. This module performs no filesystem write, network request, retrieval, or LLM call.

## Public contracts

### `FilingMetadata`

Inputs: `ticker`, `cik`, `form`, `filing_date`, `accession`, `filing_url`, optional `primary_document`, optional `exhibits`.

Output: frozen record. Ticker is uppercase; CIK contains digits without non-significant leading zeros. Filing receipt fields are non-empty; URL is HTTP(S); exhibits are a tuple. Invalid input raises `ValueError`.

### `DownloadedDocument`

Inputs: accession, form, filing date, document name, SEC source URL, relative local path, SHA-256 digest.

Output: frozen source-provenance record. Relative path cannot be absolute or traverse parent directories. Digest is exactly a lowercase 64-character hexadecimal SHA-256. Invalid input raises `ValueError`.

### `PulledCorpus`

Inputs: corpus ID, ticker, CIK, timezone-aware creation time, non-empty downloaded document tuple.

Output: frozen case-local corpus record. Documents cannot duplicate `(accession, document_name)`. `accessions` is a derived first-seen unique tuple, never caller-supplied. Invalid input raises `ValueError`.

### `SecEvidence`

Inputs: accession, form, filing date, document name, exact quote, SEC source URL.

Output: frozen citation record. Every receipt field and quote is required. Invalid input raises `ValueError`.

### `SECVerification`

Inputs: claim, verdict, confidence, plain-text explanation, supporting and contradicting evidence, material facts, missing evidence, suggested document types.

Output: frozen verifier response. Valid verdicts: `CONFIRMED`, `PARTIALLY_CONFIRMED`, `CONTRADICTED`, `INSUFFICIENT_EVIDENCE`. Confidence is within 0–1. Confirmed verdicts need supporting evidence; contradicted verdicts need contradicting evidence; insufficient-evidence verdicts need missing evidence. Explanation is required context grounded in cited evidence. Invalid input raises `ValueError`.

## Serialization contract

Every public record provides `to_dict()` and `from_dict()`. Values are JSON-safe; dates/timestamps use ISO strings; nested records reconstruct to their original type. `from_dict()` re-applies every validation rule.

## Constraints

- Standard library only.
- No Edgartools, HTTP client, filesystem, FAISS, LangChain, or LLM import.
- Public methods include purpose/input/output/failure docstrings.

## Donor code provenance

No function, class, or method in this module copies or adapts code from a repository under `reference/`. These are local contracts owned by this project.

## Tests

`tests/sec/test_schemas.py` covers ticker/CIK normalization, safe local paths, derived accessions, verifier evidence invariants, and nested verification serialization.
