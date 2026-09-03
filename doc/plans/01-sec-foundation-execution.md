# Execution Plan 01 — SEC Foundation

## Purpose

Prepare and complete the first implementation slice: deterministic SEC case/corpus foundation. This is an execution checklist, not a module specification. Detailed file and function contracts will be written only immediately before their implementation.

## Boundaries

- Build no outer agent, RAG retrieval, web/article/social/market provider, API, UI, database, or video code.
- Do not contact SEC EDGAR or any network service.
- Do not copy donor application code wholesale.
- Use this slice to establish the smallest tested foundation for later Edgartools acquisition and local SEC verification.

## Execution steps

1. Create only the first package folders: `app/sec`, `app/storage`, and matching test folders.
2. Before writing implementation, write the narrowly scoped schema/storage spec for these two modules. It must define only public records, validation behavior, case paths, and manifest persistence needed in this slice.
3. Create red tests for valid/invalid filing metadata, downloaded-document metadata, corpus manifests, case IDs, safe paths, and manifest round trips.
4. Run targeted tests. Confirm they fail because implementation does not exist or behavior is absent. Record this as red phase.
5. Implement schemas first, then run schema tests until green.
6. Implement case paths and atomic manifest persistence, then run storage tests until green.
7. Run all tests for this slice. Confirm no network fixture, client, or dependency exists.
8. Review the final public contracts against later callers: future Edgartools adapter, corpus indexer, SEC verifier, and outer-agent tool result.
9. Commit this stable foundation only if the workspace has a Git root by then.

## Donor reuse during this slice

- `reference/edgartools/edgar/entity/core.py`: inspect public `Company` usage only when beginning next acquisition slice. Do not import it yet.
- `reference/enterprise-agentic-rag-platform-ara/vectorstore/store.py`: later local-index donor; no port in this slice.
- `reference/ai-financial-research-agent/app/agent/graph.py`: later outer-loop donor; no port in this slice.

## Completion checkpoint

This step is done when contract tests pass, local files can store and reload a validated corpus manifest, and later SEC acquisition can target the established records without changing them. Next action: write the actual `app/sec` and `app/storage` module specs, then execute their red phase.

## Execution record

Completed on 2026-09-01. The module specification was written immediately before implementation. Red tests failed because the `app` package did not exist. Minimal schemas and local manifest storage were implemented; final verification passed with 10 tests. Next slice is Edgartools metadata-only filing discovery against these contracts.
