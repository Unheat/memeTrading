# Module Spec — `app/sec/corpus.py`

## Status

Completed on 2026-09-02. Red tests ran before this module was created.

## Responsibility

Prepare one existing `PulledCorpus` for later local retrieval. The module verifies receipt digests, extracts visible text from supported local SEC documents, creates deterministic citation-preserving chunks, and atomically writes a case-local JSONL artifact. It has no network or model capability.

## Public contracts

### `CorpusChunk`

Fields: `chunk_id`, `ordinal`, `accession`, `form`, `filing_date`, `document_name`, `source_url`, `relative_path`, `start_offset`, `end_offset`, `text`.

Each chunk retains the exact parent filing receipt plus offsets into the normalized source text. `chunk_id` is deterministic from corpus ID, accession, document name, and ordinal. Empty text or invalid offsets raise `ValueError`. `to_dict()` and `from_dict()` provide JSON-safe round trips.

### `CorpusPreparationError`

Fields: `code`, `message`, `retryable`. Valid codes: `INVALID_INPUT`, `MISSING_CORPUS`, `CORRUPT_CORPUS`, `UNSUPPORTED_DOCUMENT`, `EXTRACTION_FAILURE`, `STORAGE_FAILURE`.

### `CorpusPreparationResult`

Exactly one branch is populated: a successful non-empty tuple of `CorpusChunk` values plus the artifact path, or one safe `CorpusPreparationError`.

### `prepare_sec_corpus(case_directory)`

Input: existing case directory containing `sec/corpus-manifest.json` and its receipt files.

Output: completed chunk artifact or structured safe error. It must:

1. Load the manifest through `read_corpus_manifest`.
2. Resolve each recorded relative path beneath the case directory, ensure it exists and is a regular file, and recompute its SHA-256 before extraction.
3. Accept `.txt`, `.htm`, `.html`, and `.xml`; reject other extensions explicitly.
4. Decode UTF-8 first and use a deterministic lossless Latin-1 fallback. HTML/XML visible text extraction ignores `script` and `style` content. Whitespace becomes single spaces without changing document order.
5. Use named chunk-size and overlap constants. Chunks are non-empty, have stable ordinal order, and retain complete receipt metadata.
6. Atomically write `sec/index/chunks.jsonl` and `sec/index/chunks-manifest.json` only after all documents extract successfully.
7. Reuse a completed artifact only when its corpus ID, ordered document SHA-256 values, chunk count, and artifact presence match the current manifest.
8. Never make a network call, invoke a provider, parse articles, load an embedding model, create vectors, or call an LLM.

## Donor code provenance

No donor implementation is copied or adapted in this module. Standard-library text, hashing, JSON, HTML parsing, and filesystem primitives are used. `reference/enterprise-agentic-rag-platform-ara/vectorstore/store.py` is reserved for the later retrieval slice and is not used here.

## Constraints

- Artifact paths must remain beneath the supplied case directory.
- A missing, modified, or unreadable receipt file is never indexed.
- No global corpus, cross-case chunk lookup, or non-SEC input is allowed.
- Every function and method has a purpose/input/output docstring.

## Tests

`tests/sec/test_corpus.py` must cover plaintext chunk preparation, visible HTML/XML extraction, checksum mismatch, missing receipt file, unsupported extension, chunk receipt/offset invariants, no empty chunks, artifact idempotency, and no partial visible artifact after an extraction failure.

## Execution record

Initial red run: `pytest tests/sec/test_corpus.py -q` failed with five expected import errors because `app.sec.corpus` did not exist. The implementation uses only the Python standard library: `HTMLParser` for visible HTML/XML text, SHA-256 receipt verification, and atomic JSONL/JSON artifact writes. UTF-8 decoding falls back losslessly to Latin-1.

Final verification: 6 targeted corpus tests and 29 project tests passed; `python3 -m compileall -q app` passed. No network or model dependency was introduced.
