# Module Spec — Deep Research Engine

## Goal

Replace the flat bounded ReAct collector with a bounded, evidence-first research engine. The LLM chooses questions and conclusions; deterministic code admits work, preserves source/claim lineage, enforces candidate ownership, and stops honestly when coverage or budgets are incomplete.

## Contracts

`ResearchWorkItem` records a model-proposed question, depth, priority, evidence tier, dependencies, candidate ownership, and lifecycle status. `ResearchLedgerEvent` is append-only case-local audit data for planning, admission, execution, source extraction, reflection, and completion. `SourceDocument`, `SourceExcerpt`, `ResearchClaim`, and `EvidenceLink` provide claim-to-source provenance independent of ephemeral message history.

Tool accounting distinguishes model-proposed work, admitted execution, duplicate suppression, retries, and provider outcomes. A deep run is bounded by configured admitted calls, queue size/depth, reflection rounds, deadline, and phase reserves. Budget exhaustion produces `research_incomplete` with explicit gaps.

## Deep stages

1. Intake and coverage plan.
2. Bounded breadth discovery.
3. Primary-source acquisition and reading.
4. SEC/issuer evidence extraction.
5. Coverage and contradiction reflection.
6. Bounded follow-up work.
7. Candidate fan-in or explicit single-company investment gates.
8. Citation audit and synthesis.

## SEC RAG boundary

The existing corpus pipeline is canonical: filing discovery → pull → prepared chunks → FAISS/BM25/RRF retrieval → verification. `search_sec_evidence` and `read_sec_evidence` are thin outer adapters over existing corpus data; no second RAG system is created. Pulling must use validated discovered document receipts, never model-invented filing metadata.

## Donor code provenance

| Local symbol | Reuse type | Exact donor location | Deliberate changes |
| --- | --- | --- | --- |
| Work-item and bounded follow-up concept | adapted | `reference/gpt-researcher/gpt_researcher/skills/deep_research.py:259-378`, query planning and follow-up generation | Local typed queue, ledger, finance source tiers, hard budgets, and candidate ownership replace recursive execution. |
| Bounded branch concurrency concept | adapted | `reference/gpt-researcher/gpt_researcher/skills/deep_research.py:380-489`, semaphore branch execution | Local scheduler retains deterministic admission and provider/candidate budgets; donor recursion is not copied. |
| Retrieval lineage concept | adapted | `reference/storm/knowledge_storm/storm_wiki/modules/knowledge_curation.py:39-72`, dialogue query/result storage | Local source/excerpt/claim/evidence ledger retains immutable evidence rather than dialogue-only records. |
