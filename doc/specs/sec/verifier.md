# Module Spec — `app/sec/verifier.py`

## Status

Completed on 2026-09-02. Four red tests ran before this module was created.

## Responsibility

Assess one narrow claim against one indexed, case-local SEC corpus. The verifier reuses Plan-05 retrieval, gives only retrieved local chunks to an injected local assessor, validates every proposed citation, and returns a complete `SECVerification` with normal explanatory context. It does not investigate, retrieve external data, select filings, download documents, or make network calls.

## Public contracts

### `VerificationError` and `VerificationResult`

`VerificationError` exposes a stable `code`, safe `message`, and `retryable` flag. `VerificationResult` has exactly one branch: a validated `SECVerification` or an error.

Safe error codes are `INVALID_INPUT`, `RETRIEVAL_FAILED`, `ASSESSOR_UNAVAILABLE`, `INVALID_ASSESSMENT`, and `INTERNAL_FAILURE`. Internal retrieval/provider/filesystem/model details never reach the caller.

### `verify_sec_claim(case_directory, claim, embed_query, assessor, reranker=None)`

`case_directory` identifies an already-prepared, indexed local case. `claim` is a single non-empty SEC-addressable statement. `embed_query` and optional `reranker` are the existing local-only seams required by `search_sec_corpus`. `assessor` is required and receives `(claim, retrieved_chunks)`; it returns a mapping with:

```text
verdict: CONFIRMED | PARTIALLY_CONFIRMED | CONTRADICTED | INSUFFICIENT_EVIDENCE
confidence: number from 0.0 to 1.0
explanation: non-empty plain-language assessment
evidence_for_chunk_ids: list[str]
evidence_against_chunk_ids: list[str]
material_sec_facts: object/dictionary
missing_evidence: list[str]
suggested_document_types: list[str]
```

The verifier calls `search_sec_corpus` with the claim. On success it gives the assessor only the returned `RetrievedSecChunk` sequence. Every cited chunk ID must be one retrieved candidate. The verifier itself creates `SecEvidence` from the candidate's immutable `CorpusChunk` receipt and text; assessor-provided excerpts or filing metadata are ignored because the assessor may not create evidence identity.

### Verdict invariants

- `CONFIRMED` and `PARTIALLY_CONFIRMED` require one or more `evidence_for_chunk_ids`.
- `CONTRADICTED` requires one or more `evidence_against_chunk_ids`.
- `INSUFFICIENT_EVIDENCE` requires non-empty `missing_evidence`.
- A silent filing cannot be placed in `evidence_against`; lack of disclosure alone is insufficient evidence, not a contradiction.
- The assessor may list suggested SEC document types, but cannot request, select, or download them.

## Constraints

- No HTTP client, model provider SDK, MCP client, download, web/social/article/company/market call, or generic agent loop.
- No query rewriting or retrieval fallback. A retrieval failure becomes `RETRIEVAL_FAILED`.
- An absent assessor becomes `ASSESSOR_UNAVAILABLE`; do not make a keyword-only verdict or a network/model-download fallback.
- Input claim, candidate count, cited chunk IDs, explanation, missing-evidence entries, and suggested document types use named limits.
- The public boundary must run with networking disabled.

## Donor code provenance

| Local symbol | Reuse type | Exact donor location | Deliberate changes |
| --- | --- | --- | --- |
| `app.sec.verifier.verify_sec_claim` | adapted | `reference/enterprise-agentic-rag-platform-ara/app/agent.py:101-106`, `retrieve`; `reference/enterprise-agentic-rag-platform-ara/app/agent.py:109-133`, `grade_documents`; `reference/enterprise-agentic-rag-platform-ara/app/agent.py:160-210`, `generate` | Reuse Plan-05 retrieval and inject a bounded local assessor; validate a structured `SECVerification` with immutable SEC receipts; remove Ara graph state, generic conversation generation, web results, query rewrite, and all network fallback. |

## Tests

`tests/sec/test_verifier.py` must cover all verdicts and explanatory output; receipt construction; fabricated or duplicate citation IDs; malformed assessor mappings; absent assessor; retrieval failure; invalid claim; silent-filing/insufficient-evidence behavior; and no-network execution using deterministic local retrieval/assessor doubles.

## Execution record

Initial red run: `pytest tests/sec/test_verifier.py -q` failed with five expected import failures because `app.sec.verifier` did not exist. The completed module exposes `verify_sec_claim` with an injected assessor seam; it never loads or downloads a model. It maps assessor-selected retrieved chunk IDs into immutable `SecEvidence` records and rejects unknown, duplicate, cross-sided, malformed, or incomplete assessment fields before constructing `SECVerification`.

Final verification: 5 verifier tests passed, 38 project tests passed, and `python3 -m compileall -q app` passed. The graph impact check found only the new verifier tests as callers; the only production dependency is the existing local `search_sec_corpus` function.
