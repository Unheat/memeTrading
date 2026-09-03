# Execution Plan 06 — Constrained Local SEC Claim Verifier

## Purpose

Turn the Plan-05 citation-preserving local retrieval result into the one SEC capability-agent contract: a narrow claim assessment returning `SECVerification`. It answers a supplied claim against exactly one prepared, case-local SEC corpus and supplies both a plain-language explanation and exact SEC evidence. It is not an outer investigator, web researcher, document downloader, or generic chat/RAG assistant.

## Boundary

```text
outer agent supplies corpus_id + narrow claim
                    |
                    v
case-local hybrid retrieval (Plan 05)
                    |
                    v
bounded local evidence candidate set
                    |
                    v
constrained local claim assessor
                    |
                    v
SECVerification: verdict + explanation + cited evidence + missing evidence
                    |
                    v
outer agent decides whether to research, pull more filings, or finish
```

- The verifier receives no social, article, market, company-research, web-search, or network capability.
- It selects no ticker, accession, filing, exhibit, future outer action, or additional source. Only the outer agent can call `list_sec_filings` or `pull_sec_filings`.
- The verifier evaluates one claim at a time. A claim not addressable by the supplied SEC corpus must return `INSUFFICIENT_EVIDENCE`; absence of a disclosure is never automatically contradiction.
- This plan does not implement the outer LangGraph loop, an MCP server, scheduled automation, article RAG, query rewriting, or model download.

## Donor code provenance to record before implementation

The matching module spec must contain this per-function table before production code is written:

| Local symbol | Reuse type | Exact donor location | Deliberate changes |
| --- | --- | --- | --- |
| `app.sec.verifier.verify_sec_claim` | adapted | `reference/enterprise-agentic-rag-platform-ara/app/agent.py:101-106`, `retrieve`; `:109-133`, `grade_documents`; `:160-210`, `generate` | Use existing case-local retrieval rather than Ara's global workflow; assess one supplied claim; return validated `SECVerification`, evidence receipts, and missing evidence rather than a generic answer; remove all web fallback and query-routing behavior. |

Do not copy Ara's `route_query`, `rewrite_query`, Tavily/web-search logic, global graph state, generic chat messages, or API route. If the implementation does not adapt any listed behavior, remove that provenance row rather than claiming reuse.

## Required behavior

1. Accept a non-empty narrow claim, one local case directory/corpus reference, local retrieval callables, and an injected local-only assessor seam. Reject malformed input with a structured safe error.
2. Retrieve only through `search_sec_corpus`; pass the claim as the retrieval query and retain all returned receipt metadata.
3. Give the assessor only the claim plus the bounded retrieved evidence candidates. It returns a proposed verdict, plain-language explanation/context, cited chunk IDs classified for/against, material SEC facts, missing evidence, and suggested document types.
4. Validate every assessor citation against the retrieved candidate set and construct `SecEvidence` only from the immutable local receipt. The assessor cannot fabricate accession, form, date, URL, excerpt, or citation identity.
5. Enforce verdict rules: `CONFIRMED` needs supporting evidence; `PARTIALLY_CONFIRMED` identifies the supported and unresolved portions; `CONTRADICTED` needs counter-evidence; `INSUFFICIENT_EVIDENCE` explains what the supplied corpus lacks. All verdicts retain a normal explanatory response.
6. Preserve neutral uncertainty. A filing that is silent on the claim is not counter-evidence. The verifier must say when the outer agent should consider another SEC document type without asserting that it exists.
7. Default production behavior fails safely when no approved preinstalled local assessor is configured. It must not silently contact a hosted model, download a model, invoke a provider, or substitute a keyword-only verdict.
8. Keep named caps for claim length, retrieved candidates, evidence citations, explanation length, and suggested document types. Return safe failures for missing/corrupt index, retrieval failure, invalid assessor response, invalid citations, or unavailable local assessor.
9. Guarantee no-network execution in tests and through the public verifier boundary.

## Files expected during implementation

```text
doc/specs/sec/verifier.md
app/sec/verifier.py
tests/sec/test_verifier.py
```

Existing `app/sec/schemas.py` may change only if its matching spec is updated first and a verifier contract test demonstrates the need. Do not change retrieval semantics, corpus preparation, acquisition, or storage merely to make assessment convenient.

## Execution steps

1. Refresh code graphs for this project and Ara. Read only the donor functions listed above plus the current `SECVerification`, `SecEvidence`, and `search_sec_corpus` contracts.
2. Confirm the current schema can represent every required response field. If a contract gap exists, update `doc/specs/sec/schemas.md`, add red schema tests, then change the schema before writing verifier code.
3. Write `doc/specs/sec/verifier.md` immediately before production code. Define the public function/result/error contracts, injected assessor response schema, immutable citation conversion, verdict invariants, named limits, local-model configuration, and no-network guarantee. Include the exact provenance table.
4. Create red tests using Plan-05 local fixture retrieval plus deterministic assessor doubles. Cover confirmed, partially confirmed, contradicted, and insufficient-evidence responses; normal explanation; evidence-for/evidence-against receipts; silent filing behavior; fabricated/unknown citation IDs; malformed assessor response; missing index; unavailable assessor; case containment; and networking disabled.
5. Run targeted tests and record the expected red failure before creating `app/sec/verifier.py`.
6. Implement the narrow verifier. Reuse Plan-05 retrieval; validate the assessor output before constructing `SECVerification`; do not implement a generic agent loop or external model fallback.
7. Run targeted tests until green, then all project tests and compilation. If a preinstalled local assessor exists, perform one separately marked smoke test with networking disabled; otherwise record the safe unavailable-assessor behavior as the production-default check.
8. Refresh graph, trace consumers, and update this plan and the module spec with actual donor use, schema adjustments, dependencies, tests, and deferred local-assessor setup.

## Done checkpoint

Given one local SEC corpus, a narrow claim, and an injected local-only assessor, the verifier returns a validated `SECVerification` with a normal explanatory response, exact local SEC citations, material facts, and missing evidence while networking is disabled. The outer-agent implementation can later expose it as `verify_sec_claim` without granting it investigation authority.

## Execution record

Completed on 2026-09-02. `app/sec/verifier.py` adapts Ara's retrieve/grade/generate concepts through the existing case-local retrieval function and a narrow injected assessor contract. It does not copy Ara's graph state, generic conversation response, web result path, query rewriting, Tavily use, or API route.

The per-file verifier specification was written first. Red phase: 4 expected `ModuleNotFoundError` failures occurred before the module existed; a fifth test was then added for malformed assessment and invalid-claim coverage. The implementation validates an assessor's bounded structured response, builds evidence only from retrieved immutable chunk receipts, rejects fabricated/duplicate/cross-sided citations, and returns safe failures for missing retrieval and unavailable/invalid assessors. It contains no model-loading or network path.

Final verification: `pytest tests/sec/test_verifier.py -q` passed 5 tests; `pytest -q` passed 38 tests; and `python3 -m compileall -q app` passed. The graph impact trace found only the new verifier tests as callers and the existing local `search_sec_corpus` as the production dependency. A local-model smoke test is deferred: the production default intentionally returns `ASSESSOR_UNAVAILABLE` until an approved preinstalled local assessor adapter is configured.
