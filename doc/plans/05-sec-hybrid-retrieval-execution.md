# Execution Plan 05 — Case-Local SEC Hybrid Retrieval

## Purpose

Adapt Ara’s proven hybrid retrieval algorithm to the prepared case-local SEC chunks: dense FAISS search plus BM25 sparse search, reciprocal-rank fusion (RRF), and CrossEncoder reranking. The result is cited local chunk candidates for a later verifier, not a natural-language answer or verdict.

## Boundary

```text
local chunks from Plan 04
        |
        v
build_sec_index()
  local embeddings + FAISS + BM25
        |
        v
search_sec_corpus(query)
  dense + sparse + RRF + rerank
        |
        v
citation-preserving retrieved chunks
        |
        v
future verifier evaluates evidence
```

- One index belongs to one case-local corpus; no global index and no cross-case retrieval.
- Input is only the local chunk artifact created by `prepare_sec_corpus`.
- Querying/building never calls web search, SEC, social, articles, market data, company research, downloader, or an LLM.
- Embedding and reranker model artifacts must already be local. Runtime model download is prohibited because the future verifier boundary has no network.
- This plan does not implement query rewriting, evidence grading, claim verdicts, LangGraph, or outer-agent tool registration.

## Donor code provenance to record before implementation

The matching module spec must contain this per-function table before production code is written:

| Local symbol | Reuse type | Exact donor location | Deliberate changes |
| --- | --- | --- | --- |
| `app.sec.retrieval.build_sec_index` | adapted | `reference/enterprise-agentic-rag-platform-ara/vectorstore/store.py:39-63`, `build_index` | Case-local input/output; preserve `CorpusChunk` receipts; injected/local-only embedding provider; no global `STORE_DIR`; no pickle metadata. |
| `app.sec.retrieval.search_sec_corpus` | adapted | `reference/enterprise-agentic-rag-platform-ara/vectorstore/store.py:81-127`, `hybrid_search` | Return chunk IDs/receipts and scores; retain duplicate text safely; local-only artifacts; structured failures instead of generic dictionaries. |
| local reranker adapter, if ported | adapted | `reference/enterprise-agentic-rag-platform-ara/embeddings/embedder.py:30-43`, `rerank` | Return scored chunk IDs rather than locating results by text equality; use only an already-local model. |

Do not copy Ara’s global store configuration, `pickle` persistence, logging, web fallback, or generic output schema. If a planned symbol is not actually adapted, remove its provenance row rather than claiming reuse.

## Required behavior

1. Load and validate only the current local `chunks.jsonl` plus its preparation manifest. Refuse stale/corrupt/missing artifacts.
2. Build case-local FAISS dense and BM25 sparse indexes with a named index-version/model identity manifest. Source chunk ID order is immutable within an index version.
3. Permit injectable deterministic embedding and reranker seams for network-free tests. Production defaults must fail safely when configured local model artifacts or dependencies are unavailable; they must never fetch models.
4. For each query, retrieve named top-N dense and sparse candidates; remove invalid FAISS IDs; fuse ranked lists using named RRF constants; deduplicate by chunk ID.
5. Rerank fused candidates with a local CrossEncoder when available. Preserve original RRF rank as a fallback if reranking is unavailable, and return an explicit reliability/status marker.
6. Return `RetrievedSecChunk` records containing the complete `CorpusChunk` receipt plus dense/sparse/RRF/rerank scores or ranks needed for audit.
7. Store index files only below `cases/<case_id>/sec/index/`; atomically write a JSON metadata manifest. Never mutate chunk artifacts.
8. Return structured safe errors for invalid query, missing/stale corpus preparation, dependency/model absence, invalid vectors, index storage failure, or corrupted index. Never expose raw provider/model/filesystem exceptions.
9. Keep named limits for query length, index candidates, final results, vector dimension, and rerank candidates. No magic numbers.

## Files expected during implementation

```text
doc/specs/sec/retrieval.md
app/sec/retrieval.py
tests/sec/test_retrieval.py
requirements.txt
```

Do not alter `app/sec/corpus.py` or its schema unless a test exposes a concrete contract gap. If an existing production file changes, update its matching per-file spec first.

## Execution steps

1. Refresh code graphs for this project and Ara. Read only donor functions listed in the provenance table plus their immediate embedding/reranking contracts.
2. Check official package documentation and compatible versions for FAISS, BM25, and local sentence-transformer/CrossEncoder use before declaring dependencies. Do not guess APIs or allow model download at runtime.
3. Write `doc/specs/sec/retrieval.md` immediately before production code. Define public result/error/index contracts, exact provenance map, local-model configuration, index invalidation, ranking behavior, and no-network guarantees.
4. Create red tests using local Plan-04 chunk artifacts plus deterministic fake embedder/reranker. Cover dense-only, sparse-only, RRF ordering, duplicate chunk text with distinct IDs, rerank ordering, missing local model/dependency, bad vector dimension, stale artifact rejection, case containment, and no-network enforcement.
5. Run targeted tests and record expected red failure before creating `app/sec/retrieval.py`.
6. Implement the narrow retrieval adapter. Adapt only Ara’s algorithm; preserve receipt metadata and remove its global store/pickle/generic-output assumptions.
7. Run targeted tests until green, then all project tests and compilation. Perform one separately marked local-model smoke test only when model artifacts are preinstalled locally; it must make no network request.
8. Refresh graph, trace callers/consumers, and update the module spec plus this plan with actual dependencies, donor lines, test results, and any deferred local-model setup.

## Done checkpoint

Given prepared case-local SEC chunks and injected local model seams, retrieval returns deterministic, citation-preserving ranked evidence candidates through BM25 + FAISS + RRF + reranking with networking disabled. The following plan can add constrained claim assessment and the `SECVerification` verdict without changing retrieval or granting network access.

## Execution record

Completed on 2026-09-02. `app/sec/retrieval.py` adapts Ara’s `build_index` and `hybrid_search` algorithms exactly as recorded in the module-spec provenance table. It uses case-local FAISS index files, rebuilds BM25 from local chunk artifacts, applies RRF, preserves duplicate text by chunk ID, and accepts a local injected reranker returning chunk-ID scores. No Ara global store, pickle, web fallback, generic output, or model download behavior was copied.

`faiss-cpu>=1.13,<2`, `numpy>=2.0,<3`, and `rank-bm25>=0.2,<1` are declared; installed verification used FAISS 1.15.0 and rank-bm25 0.2.2. Red phase recorded four expected import failures. Final verification: 4 retrieval tests passed, 33 project tests passed, and application compilation passed. The graph impact check found only new tests as callers.
