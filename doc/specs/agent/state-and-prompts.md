# Module Spec — `app/agent/state.py` and `app/agent/prompts.py`

## Responsibility

Define the public research request, bounded execution budget, universal investigation state, and the one LLM-directed research prompt. No request profile or mode chooses an execution graph.

## `ResearchRequest` and intent

`query` is required. Optional `ticker`, `company`, `theme`, and `mandate` are caller facts, not routing controls. `depth` is `standard` or `deep`; `BudgetLimits` defaults to 35 total tool calls and two identical calls.

`resolve_intent()` preserves only explicit structural requirements: caller-provided subjects, a requested count (`top 10`, `best 5`, `rank 3`, or `compare 4`), candidate-workspace requirement, and an explicit capital-allocation request. It never classifies prompt keywords, picks a research graph, creates candidates, or decides a recommendation.

`InvestigationState` stores `research_intent`, universal source/evidence/receipt containers, optional single-company facts, and candidate-owned workspaces. It does not contain `profile` or `mode`.

## Prompt contract

`build_research_system_prompt(state)` provides the LLM with its full user-directed intent, current evidence, candidate state, contradictions, and remaining tool budget. For comparisons/rankings it instructs the LLM to register each candidate before company-specific tool calls and to pass the registered candidate ID to all market/SEC/corpus operations. The LLM decides the plan and sources; deterministic code only enforces budgets and identity ownership.

## Context policy

`ModelContextPolicy` supports up to a 1M-token context window with a conservative 200,000-token compaction threshold when reliable provider metadata is unavailable. Assistant tool calls and their matching results are retained/pruned as complete pairs; permanent structured facts are reprojected through the universal prompt.

## Donor code provenance

| Local symbol | Reuse type | Exact donor location | Deliberate changes |
| --- | --- | --- | --- |
| `app.agent.state.InvestigationState` baseline message state | adapted | `reference/ai-financial-research-agent/app/agent/state.py:10-35`, `SimpleAgentState` | Local universal research intent, evidence ledger, budget, candidate isolation, and forensic fields replace the donor's simple state. |
| `app.agent.state.ResearchIntent` | locally written | N/A | Preserves explicit prompt constraints without implementing keyword routing. |
| `app.agent.prompts.build_research_system_prompt` | locally written | N/A | One prompt-directed contract with candidate ownership and no profile/mode branch. |
