# Module Spec — Universal LLM-Directed Deep Research

## Goal

Run every user request through one bounded deep-research graph. The LLM reads the full prompt, plans the work, selects tools, discovers entities, collects evidence, and synthesizes the answer. The application must not classify prompt keywords into generic, screen, or single-ticker execution modes.

## Public request contract

`ResearchRequest.query` is the required public input. Optional `ticker`, `company`, `theme`, and `mandate` fields provide explicit caller facts but do not select a graph.

`ResearchRequest.resolve_intent()` extracts only structural constraints that deterministic code must preserve:

- an explicitly requested ranking count such as `top 10`, `best 5`, `rank 3`, or `compare 4`;
- explicit caller-supplied targets;
- whether a ranking/comparison requires candidate-owned workspaces;
- whether the prompt explicitly requests a capital-allocation decision.

It never chooses a research route, candidate list, investment conclusion, or hard-coded output count.

## Universal workflow

```text
user prompt → LLM-directed bounded tool loop → durable evidence ingestion
→ prompt-appropriate evidence completion → report
                                   └→ explicit single-company position request only:
                                      G1–G4 validation → committee
```

The same graph and full research registry serve general research, comparison/ranking requests, and named-company research. Tool budgets, duplicate-call limits, schemas, and evidence ownership remain deterministic safeguards.

## Candidate ranking safety contract

For a multi-candidate request, the LLM must:

1. discover and register each company with `register_candidate`;
2. pass the returned `candidate_id` to every company-specific market, consensus, SEC financial, filing, pull, and SEC-claim verification call;
3. collect evidence independently in each candidate workspace;
4. call `compare_candidates` after collection;
5. state ranking incompleteness if fewer than the prompt-requested count are evidence-backed.

Candidate-scoped payloads may update only their registered workspace. Unknown IDs, absent IDs in candidate research, mismatched tickers, and invalid ownership are recorded as error receipts and never fall back to global company fields. Ranking requests always report `allocation_pct: 0.0`; they cannot enter sizing or media generation merely because the prompt discusses stocks.

## Completion policy

- General research completes when it has usable sources or durable evidence; otherwise it reports `research_incomplete` with gaps.
- A ranking completes only when the requested count of candidates each has market plus SEC/primary evidence and a normalized comparison exists.
- Explicit single-company investment decisions may enter G1–G4 only after normal collection and only when market/SEC identity, liquidity, corpus/evidence, and receipts satisfy the existing gates.

## Artifacts and provenance

Receipts retain tool call IDs plus returned routing identity (`candidate_id`, ticker, CIK, corpus ID where present). Case manifests include the resolved research intent. Sources remain distinct from grounded evidence.

## Donor code provenance

| Local symbol | Reuse type | Exact donor location | Deliberate changes |
| --- | --- | --- | --- |
| Bounded agent/tool loop concept | adapted | `reference/ai-financial-research-agent/app/agent/graph.py:68-92,129-225`, graph loop | Local graph has one prompt-driven entry path, durable ingestion, context policy, candidate isolation, and deterministic gates. |
| Plan → bounded acquisition concept | adapted | `reference/gpt-researcher/gpt_researcher/skills/researcher.py:50-95,362-395`, planning and bounded acquisition | Local model-directed plan uses typed state, budget guards, receipts, and claim/evidence separation. |
| Candidate isolation fan-out constraint | adapted | `reference/investment-research/contracts/orchestrator.yaml:15-35`, per-ticker fan-out/fan-in | Local implementation keeps a single graph and candidate-owned state; no donor multi-agent architecture copied. |
