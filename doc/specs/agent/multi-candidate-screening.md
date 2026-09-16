# Module Spec — Candidate-Owned Research Evidence

## Goal

Support LLM-directed ranking and comparison requests without requiring a ticker or forcing a screen workflow. The prompt determines the requested companies and ranking count. Candidate workspaces provide deterministic isolation so evidence cannot cross companies.

## Contract

- No public `mode`, `profile`, `screen`, or `single_ticker` field exists.
- `ResearchRequest.resolve_intent()` preserves an explicit prompt count (`top 10`, `best 5`, `rank 3`, or `compare 4`) but does not select a research path.
- For ranking/comparison intent, company-specific tool calls require a previously registered `candidate_id`.
- A candidate result is accepted only when its returned ticker matches that registered candidate. Unknown IDs, missing IDs, and ticker mismatches are quarantined as error receipts.
- Candidate-owned market, consensus, SEC financials, filing CIKs, corpora, evidence, and contradictions never update global single-company fields.
- `pull_sec_filings` stores candidate artifacts beneath `cases/<case_id>/candidates/<candidate_id>/`.
- A ranking completes only when the requested number of candidates each has market plus SEC/primary evidence and a comparison record exists. Otherwise status is `research_incomplete`, with the requested and collected evidence-backed counts reported.
- Ranking outputs have no allocation or media artifact. Explicit single-company position requests are the only entry to investment G1–G4 validation.

## Fact and comparison models

`CandidateResearchState` owns company identity, market context, consensus, SEC financials, corpora, evidence, contradictions, and fact cards. `FactCard` is an atomic cited financial datum. `ComparisonCard` represents comparable, mismatched, or unavailable metrics. `compare_candidates` records the model-requested candidate/metric comparison; the report may not call a candidate a winner without its independent evidence.

## Test requirements

`tests/agent/test_screening.py` and the all-tools E2E test must prove:

1. candidate state round-trips;
2. candidate-scoped market/SEC data does not populate global state;
3. mismatched or unknown candidate results are error receipts;
4. requested ranking counts are honored and insufficient evidence is not presented as a shortlist;
5. every registered tool can run in dependency order with candidate-owned SEC corpus/evidence retained.

## Donor code provenance

| Local symbol | Reuse type | Exact donor location | Deliberate changes |
| --- | --- | --- | --- |
| `app.agent.screening.CandidateLead` | adapted | `reference/investment-research/schemas/candidate-list.schema.json:1-45`, candidate items | Adapted to a Python discovery-lead dataclass. |
| `app.agent.screening.ScreenCandidate` | adapted | `reference/investment-research/contracts/screener.yaml:1-25`, candidate output | Simplified to core identification fields. |
| `app.agent.screening.ComparisonCard` | adapted | `reference/investment-research/contracts/orchestrator.yaml:15-35`, multi-branch comparisons | Adapted to a local normalized comparison model. |
| `app.agent.screening.FactCard` | adapted | `reference/investment-research/schemas/evidence-item.schema.json:1-35`, evidence item | Mapped to a candidate-owned cited metric unit. |
