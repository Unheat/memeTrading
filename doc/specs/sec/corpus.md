# Module Spec — `app/sec/corpus.py`

## Status

Completed on 2026-09-02. Red tests ran before this module was created.

Updated 2026-10-04: section-aware ingestion upgrade — HTML/XML documents are pre-parsed with the
`edgartools` structured document parser so primary filings (10-K, 10-Q, 8-K) yield section-tagged
chunks with Markdown pipe tables, while exhibits, unsectioned documents, and parse failures keep the
original visible-text fallback unchanged.

## Responsibility

Prepare one existing `PulledCorpus` for later local retrieval. The module verifies receipt digests, extracts visible text from supported local SEC documents, creates deterministic citation-preserving chunks, and atomically writes a case-local JSONL artifact. It has no network or model capability.

## Public contracts

### `CorpusChunk`

Fields: `chunk_id`, `ordinal`, `accession`, `form`, `filing_date`, `document_name`, `source_url`, `relative_path`, `start_offset`, `end_offset`, `text`, `section`.

Each chunk retains the exact parent filing receipt plus offsets into the normalized source text. `section` is the canonical section label stamped by the structured parser (for example `Item 1A - Risk Factors`, `Item 7 - MD&A`, `Item 1.01 - Entry into Material Agreement`) or `None` when the chunk came from an unsectioned document or the plaintext/fallback path. Offsets are relative to the text stream the chunk was cut from (the section text for sectioned chunks, the whole normalized document text otherwise). `chunk_id` is deterministic from corpus ID, accession, document name, and ordinal. Empty text or invalid offsets raise `ValueError`. `to_dict()` and `from_dict()` provide JSON-safe round trips; `from_dict()` accepts legacy artifacts that lack the `section` key because the field defaults to `None`.

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
4. Decode UTF-8 first and use a deterministic lossless Latin-1 fallback. HTML/XML extraction is section-aware:
   - For `.htm`/`.html`/`.xml`, first attempt the `edgartools` structured document parser (see dependency boundary below) with the document's own `form` value. When the parser detects sections, iterate them in document order (sorted by `start_offset`), render each section with `Section.markdown()` (Markdown pipe tables preserved), unescape Markdown backslash-punctuation escapes, and chunk each section with the standard chunker, stamping every chunk with the section's canonical title.
   - When no sections are detected, the form is unknown, the document is a `.txt` exhibit, or the structured parser raises or yields no visible text, fall back to the original standard-library visible-text extraction (ignoring `script` and `style`) and produce untagged chunks (`section=None`). Whitespace in the fallback path becomes single spaces without changing document order.
   - Sectioned chunk text preserves newlines and pipe-table rows so column alignment survives indexing; the fallback path keeps the legacy single-space normalization.
5. Use named chunk-size and overlap constants. Chunks are non-empty, have stable ordinal order across the whole document (sectioned sections are numbered in document order), and retain complete receipt metadata.
6. Atomically write `sec/index/chunks.jsonl` and `sec/index/chunks-manifest.json` only after all documents extract successfully.
7. Reuse a completed artifact only when its corpus ID, ordered document SHA-256 values, chunk count, and artifact presence match the current manifest.
8. Never make a network call, invoke a provider, parse articles, load an embedding model, create vectors, or call an LLM.

## Donor code provenance

No donor implementation is copied or adapted in this module. Standard-library text, hashing, JSON, HTML parsing, and filesystem primitives are used. `reference/enterprise-agentic-rag-platform-ara/vectorstore/store.py` is reserved for the later retrieval slice and is not used here.

## Dependency boundary (black-box)

`edgartools` (declared in `requirements.txt` as `edgartools>=5.55,<6`; verified against 5.58.0) is used as a black-box dependency for structured HTML/iXBRL parsing. Relevant public API: `edgar.documents.HTMLParser.create_for_ai()`, `edgar.documents.config.ParserConfig` (the `form` attribute is required for section detection), `HTMLParser.parse(html_or_bytes) -> Document`, `Document.sections` (a `dict[str, Section]` keyed by canonical name with `Section.title/item/part/start_offset/markdown()`). Section detection without `form` returns no sections, so the parser is always configured with the parent document's own form value from the pull receipt. No donor source is copied; all chunking, receipt stamping, fallback, and artifact logic remains local.

## Constraints

- Artifact paths must remain beneath the supplied case directory.
- A missing, modified, or unreadable receipt file is never indexed.
- No global corpus, cross-case chunk lookup, or non-SEC input is allowed.
- Every function and method has a purpose/input/output docstring.

## Tests

`tests/sec/test_corpus.py` must cover plaintext chunk preparation, visible HTML/XML extraction, checksum mismatch, missing receipt file, unsupported extension, chunk receipt/offset invariants, no empty chunks, artifact idempotency, and no partial visible artifact after an extraction failure. The section-aware upgrade additionally requires: section tagging of chunks from a multi-item HTML filing, Markdown pipe-table preservation for a sectioned table, legacy fixture compatibility (`Binding agreement`), and legacy `chunks.jsonl` artifacts without the `section` key remaining loadable via `from_dict`.

## Execution record

Initial red run: `pytest tests/sec/test_corpus.py -q` failed with five expected import errors because `app.sec.corpus` did not exist. The implementation uses only the Python standard library: `HTMLParser` for visible HTML/XML text, SHA-256 receipt verification, and atomic JSONL/JSON artifact writes. UTF-8 decoding falls back losslessly to Latin-1.

Final verification: 6 targeted corpus tests and 29 project tests passed; `python3 -m compileall -q app` passed. No network or model dependency was introduced.
