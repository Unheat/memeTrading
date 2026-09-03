# Execution Plan 03 — Controlled SEC Corpus Pull

## Purpose

Implement `pull_sec_filings`, the narrow acquisition step between metadata discovery and the local SEC RAG verifier. It turns explicitly selected filing metadata into one case-local `PulledCorpus` with receipt metadata and validated local files. It does not index, retrieve, rerank, call an LLM, or verify a claim.

## Why this comes before RAG

The verifier must never download documents. It can only search a complete local corpus chosen by the outer agent. This slice establishes that boundary and provides stable inputs for the later BM25, FAISS, RRF, and reranking work.

```text
list_sec_filings() metadata
        |
        v
pull_sec_filings() downloads selected SEC material
        |
        v
case-local PulledCorpus
        |
        v
future local-only RAG index and verifier
```

## Boundaries

- Use the existing `FilingMetadata`, `DownloadedDocument`, `PulledCorpus`, and case-manifest contracts.
- Caller explicitly supplies one ticker and selected filing metadata. No autonomous filing selection or ticker switching.
- Fetch only requested filing primary documents and explicitly permitted material exhibits. Never bulk-ingest a company history.
- Use Edgartools or SEC URLs only through a thin acquisition adapter; do not port donor download code.
- Keep all network behavior out of unit tests with injected fetchers.
- Do not build the RAG index, use LangChain/LangGraph, call an LLM, search the web, or add an outer agent.
- Preserve source URL, accession, form, filing date, document name, SHA-256 checksum, and case-relative path for every stored item.

## Required behavior

`pull_sec_filings` must:

1. Validate a caller-created case ID and selected `FilingMetadata` values belong to the requested ticker.
2. Enforce named limits for filing count, document bytes, and allowed exhibit count; reject over-limit input before any fetch where possible.
3. Fetch each requested source through an injected/default downloader with an SEC-compliant identity and timeout policy.
4. Persist content only under `cases/<case_id>/sec/`; generate safe deterministic file names without using provider names directly as paths.
5. Compute SHA-256 and create `DownloadedDocument` records.
6. Return a complete `PulledCorpus` only after every selected document is safely written; clean up incomplete files on failure.
7. Write a corpus manifest atomically through the existing storage module after successful acquisition.
8. Return structured, recoverable errors for invalid selection, unavailable source, unsafe content/path, size limit, or storage failure. Never expose provider exceptions directly.
9. Make repeated calls for an already identical source idempotent: reuse a matching checksum-backed local document instead of downloading it again.

## Files expected during implementation

```text
doc/specs/sec/pull.md
app/sec/pull.py
tests/sec/test_pull.py
```

The existing `app/sec/schemas.py` and `app/storage/cases.py` may receive minimal contract additions only if tests expose a real missing field or helper. Any production-file change gets its matching per-file spec updated first.

## Execution steps

1. Refresh the local code graph. Inspect only the exact schema and case-storage symbols this slice consumes, plus Edgartools public download APIs and official documentation. Confirm supported public behavior before code.
2. Create `doc/specs/sec/pull.md` immediately before the production module. Define public input/result/error types, selection rules, safe path rules, idempotency, atomicity, and no-network verifier boundary.
3. Write red unit tests using an injected fake downloader and temporary case root. Cover primary filing success, explicit exhibit success, receipt/checksum/manifest output, unknown selection, mismatched ticker, source failure, byte limit, unsafe document name, cleanup after a partial failure, and idempotent rerun.
4. Run the targeted test file and record its expected red failure before creating `app/sec/pull.py`.
5. Implement the smallest downloader adapter and filesystem writer. Reuse existing schema validation and atomic manifest writer; add no RAG dependency.
6. Run targeted tests until green, then run the whole suite and compile application code.
7. Perform impact analysis for callers and contracts. Refresh the graph after code is complete.
8. Update this plan and `doc/specs/sec/pull.md` with actual API assumptions, test results, and any deferred live SEC smoke test.

## Reference boundary

- `reference/edgartools/` is a black-box library. Use public APIs only after verification; never copy its SEC transport code.
- `reference/enterprise-agentic-rag-platform-ara/vectorstore/store.py` is not used in this slice. Its hybrid retrieval becomes relevant only after a local corpus exists.

## Done checkpoint

One selected set of SEC filings/exhibits can become a validated, case-local corpus with auditable receipts and no partial visible corpus on failure. Unit tests are network-free. The next plan may build local corpus preparation and hybrid retrieval, without adding internet access to the verifier.

## Execution record

Completed on 2026-09-02. The precise outer-agent hand-off is `SelectedSecDocument(filing, document_name, source_url)`: the agent supplies the exact accession/document records it selected after discovery. `app/sec/pull.py` creates one case-local corpus, validates SEC-only URLs and declared document names, stores SHA-256 receipts, writes the existing atomic manifest, removes invocation-created files after failure, and reuses an identical completed corpus without redownloading.

The live downloader uses Python standard-library HTTP, requires `SEC_USER_AGENT`, has a 10 MiB document limit, and serializes default SEC requests at a 0.11-second interval. Tests use injected fake downloaders and perform no network I/O. Red phase recorded six expected import failures before the module existed. Final verification: `pytest tests/sec/test_pull.py -q` passed 7 tests; `pytest -q` passed 23 tests; `python3 -m compileall -q app` passed. Live smoke check deferred because SEC identity is not configured.
