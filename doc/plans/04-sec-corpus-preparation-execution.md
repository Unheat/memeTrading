# Execution Plan 04 — Local SEC Corpus Preparation

## Purpose

Turn an already completed `PulledCorpus` into validated, case-local, citation-preserving text chunks. This is the first internal RAG preparation step. It enables the later BM25, FAISS, reciprocal-rank fusion, and reranking slice, but does not implement any retrieval, model, or verifier yet.

## Why this is next

The puller now gives the verifier immutable SEC bytes plus source receipts. Search must never index bytes blindly: it first needs deterministic text extraction, digest verification, chunk boundaries, and receipt links. Building this separately keeps the later hybrid-retrieval behavior testable without an LLM or network.

```text
PulledCorpus + case-local SEC files
        |
        v
verify manifest and SHA-256 receipts
        |
        v
extract supported local SEC text
        |
        v
deterministic citation-preserving chunks
        |
        v
future local BM25 + FAISS retrieval
```

## Boundaries

- Input is one existing case directory and its `PulledCorpus` manifest only.
- Verify every file's SHA-256 digest before extraction. A changed, missing, or unreadable file is a structured failure; never index it.
- Support local SEC `.txt`, `.htm`, `.html`, and `.xml` input first. Unsupported formats are reported explicitly, not silently discarded.
- Preserve accession, form, filing date, document name, source URL, relative path, and deterministic local chunk identity with every chunk.
- Store prepared chunks under the same case directory. No global index or cross-case retrieval.
- No network, Edgartools call, downloader, LangChain/LangGraph, LLM, embeddings, FAISS, BM25, reranker, article extraction, or outer agent.
- Do not use `trafilatura`: SEC filings require receipt-preserving document processing, not general web-article cleanup.

## Required behavior

1. Load the existing atomic corpus manifest through `read_corpus_manifest`.
2. Resolve every recorded relative path beneath its case directory and recompute the stored SHA-256 before reading it as source content.
3. Decode text deterministically, normalize whitespace without erasing document order, and remove non-visible markup only for supported local HTML/XML formats.
4. Split normalized text with named size and overlap constants. Never produce an empty chunk or a chunk without its parent receipt fields.
5. Give each chunk a deterministic ID derived from corpus ID, accession, document name, and ordinal; preserve character offsets in normalized text.
6. Atomically persist a JSONL chunk artifact and small metadata manifest below `cases/<case_id>/sec/index/`.
7. Return structured, safe failures for missing corpus, unsafe/corrupt path, digest mismatch, unsupported document, decode/extraction failure, or storage failure. Do not expose raw filesystem exceptions.
8. Make repeated preparation of unchanged source corpus idempotent: return/reuse the matching artifact rather than silently producing divergent chunks.

## Files expected during implementation

```text
doc/specs/sec/corpus.md
app/sec/corpus.py
tests/sec/test_corpus.py
```

If `CorpusChunk` or a preparation result/error type belongs in `app/sec/schemas.py`, update [its matching module spec](../specs/sec/schemas.md) before changing that production file. No other production module may change without its matching per-file spec.

## Execution steps

1. Refresh the local code graph. Inspect the existing `PulledCorpus`, `DownloadedDocument`, `read_corpus_manifest`, and path-safety behavior.
2. Inspect Ara only for its case-local index boundary; do not port its global store or retrieval code in this slice.
3. Write `doc/specs/sec/corpus.md` immediately before production code. Define chunk/result/error contracts, supported-format behavior, text normalization, named limits, artifact layout, citation metadata, and idempotency.
4. Write red tests using a temporary case and `pull_sec_filings` with fake bytes. Cover plaintext, HTML/XML visible-text extraction, digest mismatch, missing file, unsupported extension, deterministic chunk boundaries/metadata, no empty chunks, atomic artifact write, and idempotent rerun.
5. Run targeted tests and record expected red failure before creating production code.
6. Implement the smallest local-only corpus preparer using standard-library parsing where sufficient. Add a dependency only after verifying a real SEC-format limitation that the standard library cannot safely handle.
7. Run targeted tests until green, then all project tests and Python compilation.
8. Perform graph-based impact analysis, refresh the graph, and update this plan plus every touched per-file spec with actual results.

## Reference boundary

- `reference/enterprise-agentic-rag-platform-ara/vectorstore/store.py` informs only the later retrieval artifact boundary. Its global paths, web fallback, and generic application state are excluded.
- `reference/edgartools/` is not called here. This slice reads only files already acquired by `app/sec/pull.py`.

## Done checkpoint

A completed SEC corpus produces an auditable local text-chunk artifact whose every chunk points back to its exact filing receipt and source file. It runs with networking disabled. The following plan can add hybrid BM25/FAISS retrieval over those chunks without changing acquisition or allowing verifier network access.

## Execution record

Completed on 2026-09-02. `app/sec/corpus.py` reads only the existing local corpus manifest and receipt files. It verifies every SHA-256 before extraction; supports `.txt`, `.htm`, `.html`, and `.xml`; preserves receipt fields and normalized-text offsets in every `CorpusChunk`; and writes `sec/index/chunks.jsonl` plus a reuse manifest. A matching existing artifact is reused without divergence.

No donor code was copied. The module uses standard-library HTML parsing, hashing, JSON, and atomic files. Red phase recorded five expected import failures. Final verification: 6 targeted corpus tests passed, 29 project tests passed, and application compilation passed. The graph impact check found only the six new tests as callers; no existing application flow changed.
