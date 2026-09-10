# Execution Plan 11 — Outer Agent Orchestration & Memo Generation

## Purpose

Implement the outer market research agent and forensic memo generator defined in `doc/fullplan.md` and `doc/mvp-spec.md` (Step 8).
The agent runs a free tool-calling loop in LangGraph against the 8 normalized research tools, maintaining a two-tier state (trimmed ephemeral raw messages + permanent structured facts). Upon completion, it deterministically renders a comprehensive, evidence-backed forensic memo (`memo.md`) and audit trail (`investigation.json`).

## Boundaries

- Exactly one outer agent owning the investigation. No specialist agent hierarchies, no bull/bear debate personas, no multi-agent supervisors.
- Exactly 8 normalized tools bound to the agent (`search_social`, `search_articles`, `read_article`, `search_web`, `get_market_data`, `list_sec_filings`, `pull_sec_filings`, `verify_sec_claim`).
- Evidence hierarchy enforced: SEC filings > regulatory sources > company primary sources > professional news/analysts > industry publications > social media (hypotheses only).
- Two-tier context management: raw messages trimmed to ~4k tokens, permanent structured state (`evidence`, `unresolved_questions`, `contradictions`, `causal_chain`) preserved in the dynamic system prompt.
- Strict budget caps (max tool calls, duplicate call caching/guard, zero information-gain stopping).
- Tests must be deterministic and offline using `ScriptedModel` fake LLM and fixture tool results (no network).

## Donor Code Provenance

| Local symbol | Reuse type | Exact donor location | Deliberate changes |
|---|---|---|---|
| `app.agent.state.InvestigationState` | adapted | `reference/ai-financial-research-agent/app/agent/state.py:10-35`, `SimpleAgentState` | Extends basic message sequence state with structured forensic fields (`root_claims`, `evidence`, `contradictions`, `unresolved_questions`, `causal_chain`, `market_context`, `budget_state`). |
| `app.agent.graph.create_agent_graph` | adapted | `reference/ai-financial-research-agent/app/agent/graph.py:25-78`, workflow and `should_continue` | Replaced rigid financial prompt and fixed tool bindings with the 8 normalized tools, duplicate call detection, and information-gain stopping conditions. |
| `app.agent.prompts` | adapted | `reference/ai-financial-research-agent` + `reference/ai-hedge-fund` (`druckenmiller.py`, `lynch.py`) | Extracted analytical investment lenses (Druckenmiller rate-of-change/pricing check, Lynch categorization, Buffett dilution check, causal chain `signal -> demand -> beneficiary -> mechanism -> expectation gap`) into a single forensic charter prompt. No persona subagents. |
| `app.agent.runner.run_investigation` | adapted | `reference/ai-financial-research-agent/app/api/service.py:40-110` | Streamlined into a standalone runner that receives a `ResearchRequest`, initializes case directories via `app.storage.cases`, runs the graph, and outputs `memo.md` + `investigation.json`. |

## Required Behavior

1. **`app/agent/state.py`**:
   - `ResearchRequest`: user query, ticker, optional company/theme/mandate/time_boundary, budget limits.
   - `InvestigationState(TypedDict)`: `messages: Annotated[list[BaseMessage], add_messages]`, `ticker`, `company`, `cik`, `case_id`, `root_claims`, `evidence`, `contradictions`, `unresolved_questions`, `sec_corpora`, `searches_performed`, `confidence`, `tool_calls`, `status`, `causal_chain`, `market_context`, `thesis_breakers`, `budget_state`.
2. **`app/agent/prompts.py`**:
   - System charter prompt incorporating forensic skepticism, evidence hierarchy, and investment lenses.
   - Dynamic prompt builder injecting structured evidence, unresolved questions, and remaining budget into system turn.
3. **`app/agent/tools.py`**:
   - Tool registry wrapping the 8 tools into LangChain tools.
   - Duplicate call detector preventing infinite loops on identical queries.
   - Structured error containment.
4. **`app/agent/context.py`**:
   - Message trimming using `trim_messages` to protect token context window while retaining dynamic system prompt.
   - Information gain and budget tracker.
5. **`app/agent/graph.py`**:
   - `StateGraph(InvestigationState)`: `agent -> tools -> agent | end`.
   - `should_continue` conditional edge checking tool call presence, budget exhaustion, and loop limits.
6. **`app/agent/memo.py`**:
   - Deterministic markdown memo renderer producing `memo.md` with trigger, hype claims, confirmed facts, contradictions, SEC citation receipts table, dilution/insider assessment, and open uncertainties.
   - JSON serializer for `investigation.json`.
7. **`app/agent/runner.py`**:
   - Orchestrates request -> case folder -> graph run -> artifact save -> returns `InvestigationResult`.

## Execution Steps

1. Write specifications in `doc/specs/agent/`.
2. Implement and test `state.py`, `prompts.py`, `context.py` (TDD).
3. Implement and test `tools.py` with duplicate detection (TDD).
4. Implement and test `graph.py` using offline `ScriptedModel` (TDD).
5. Implement and test `memo.py` and `runner.py` (TDD).
6. Run full test suite across all subsystems and commit Step 8 milestone.
