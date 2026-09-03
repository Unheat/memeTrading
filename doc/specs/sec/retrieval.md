# Module Spec — `app/sec/retrieval.py`

## Status

Completed on 2026-09-02. Red tests ran before this module was created.

## Responsibility

Build and query a FAISS + BM25 hybrid index over exactly one prepared local SEC corpus. Retrieval returns receipt-preserving ranked chunks for a later verifier; it does not generate answers or access any network.

## Public contracts

### `IndexBuildResult` and `RetrievalResult`

Each result has exactly one success or failure branch. Success returns a case-local artifact path or non-empty `RetrievedSecChunk` tuple. Failure returns a safe code: `INVALID_INPUT`, `MISSING_PREPARATION`, `STALE_PREPARATION`, `DEPENDENCY_UNAVAILABLE`, `INVALID_VECTOR`, `CORRUPT_INDEX`, or `STORAGE_FAILURE`.

### `build_sec_index(case_directory, embedder)`

`embedder(texts) -> vectors` is required. It is injected so tests use deterministic local vectors and production may use only a preinstalled local embedding model. Build verifies the current preparation manifest, validates non-empty same-dimension finite vectors, writes `sec/index/sec.faiss` and an atomic JSON index manifest, and never alters chunks.

### `search_sec_corpus(case_directory, query, embed_query, reranker=None, top_k=...)`

Loads only a matching case-local index. Dense FAISS and sparse BM25 candidates are fused by reciprocal-rank fusion. If `reranker` is supplied, `reranker(query, chunks)` returns scored chunk IDs and determines final ordering. Without it, RRF ordering is returned with `rerank_status="NOT_APPLIED"`. Every returned item includes its complete `CorpusChunk` receipt and dense/sparse/RRF/rerank audit values.

## Constraints

- `faiss-cpu`, `numpy`, and `rank-bm25` are normal dependencies; sentence-transformer/CrossEncoder loading is intentionally not implemented here.
- No network, model download, LLM, web/SEC/provider call, global index, pickle, or cross-case lookup.
- Index and metadata only live under `cases/<case_id>/sec/index/`.
- Chunk text equality is never used as identity; duplicate text remains distinct by `chunk_id`.
- Named constants control query length, candidate count, final count, RRF denominator, and vector validation.

## Donor code provenance

| Local symbol | Reuse type | Exact donor location | Deliberate changes |
| --- | --- | --- | --- |
| `app.sec.retrieval.build_sec_index` | adapted | `reference/enterprise-agentic-rag-platform-ara/vectorstore/store.py:39-63`, `build_index` | Case-local chunks, receipt metadata, JSON manifest, injected local embeddings; removes global store and pickle. |
| `app.sec.retrieval.search_sec_corpus` | adapted | `reference/enterprise-agentic-rag-platform-ara/vectorstore/store.py:81-127`, `hybrid_search` | Structured results, duplicate-safe chunk IDs, local-only index, and optional injected reranker. |

## Tests

`tests/sec/test_retrieval.py` must cover index build, dense/sparse RRF fusion, duplicate chunk text, reranker order, missing/stale preparation, invalid vector shape, and no-network execution.

## Execution record

Initial red run: `pytest tests/sec/test_retrieval.py -q` failed with four expected import errors because `app.sec.retrieval` did not exist. `faiss-cpu 1.15.0` and `rank-bm25 0.2.2` were installed and declared in `requirements.txt`; NumPy was already available. Production embedding and CrossEncoder model loading remains intentionally outside this module: callers inject local-only embedder and reranker callables, so this layer cannot download models or contact a provider.

Final verification: 4 retrieval tests and 33 project tests passed; `python3 -m compileall -q app` passed. The graph impact check found only the new retrieval tests as callers.
