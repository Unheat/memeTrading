# Module Spec — `app/agent/tools.py` and `app/agent/graph.py`

## Responsibility

Define the tool registry wrapping all 10 normalized tools for LangGraph, duplicate call containment, deterministic post-tool ingestion, adaptive context management, and the three-stage StateGraph workflow.

## `app/agent/tools.py`

Exposes `create_agent_tools(cases_root: Path | None = None)` returning a list of LangChain-compatible tools:
1. `search_social(query, ticker, time_window)` -> calls `app.social.search.search_social`.
2. `search_articles(query, ticker, sources, days, limit)` -> calls `app.articles.search.search_articles`.
3. `read_article(url)` -> calls `app.articles.reader.read_article`.
4. `search_web(query, domains, limit)` -> calls `app.websearch.search.search_web`.
5. `get_market_data(ticker, period, benchmark_ticker)` -> calls `app.market.market_data.get_market_data`.
6. `get_company_research(ticker)` -> calls `app.market.company_research.get_company_research`.
7. `list_sec_filings(ticker, forms, since)` -> calls `app.sec.acquisition.list_sec_filings`.
8. `pull_sec_filings(case_id, selections)` -> calls `app.sec.pull.pull_sec_filings`.
9. `verify_sec_claim(corpus_id, claim)` -> calls `app.sec.verifier.verify_sec_claim`.
10. `get_sec_financials(ticker, periods)` -> calls `app.sec.financials.get_sec_financials`.

The hosted SEC assessor remains an internal dependency of `verify_sec_claim`; it is excluded from the outer agent's tool registry and is never an eleventh agent tool.

### Duplicate Call Guard
Wraps tool execution with a call-signature hash `hash(tool_name, sorted_args)`:
- If a tool is called repeatedly with identical arguments within the same run, returns a structured note: `"[DUPLICATE_CALL] Identical query already performed. Use prior results."` rather than re-executing.
- Exceptions are trapped and returned as string error messages so the agent loop does not crash.

## `app/agent/graph.py`

### StateGraph Architecture
- Graph definition: `workflow = StateGraph(InvestigationState)`.
- Three stages:
  1. **Forensic Investigator**: free-loop tool-calling investigation through `"agent"`, `"tools"`, and deterministic post-tool ingestion.
  2. **Air-Gapped Adversarial Red Team**: short-seller attack, contradiction review, and kill-criteria assessment without outer-agent tool access.
  3. **Investment Committee**: CIO-style asymmetry review, passing discipline, and position sizing.
- Investigator nodes:
  - `"agent"`: Prepares the dynamic prompt, applies `ModelContextPolicy`, invokes the model with the 10 bound tools, and increments tool-call counters.
  - `"tools"`: Executes tool calls using `ToolNode` or a customized safe executor.
  - Post-tool ingestion: deterministically parses every completed tool result into permanent structured state before another model invocation. It updates applicable evidence, contradictions, unresolved questions, SEC corpora, searches, market context, consensus snapshot, expectation gap, and budget metadata without asking the model to reproduce tool payloads.
- Tool-call/result history is pair-safe: an assistant message containing tool calls and all matching tool-result messages are retained, pruned, or compacted as one exchange.
- Adaptive context management supports model windows up to 1M tokens and defaults to a 200,000-token pruning threshold when reliable model capacity metadata is absent. It uses model-aware token counting where available, then prunes older completed exchanges before compaction. Provider-native context management is optional and capability-gated; portable local handling remains required.
- Conditional Edge `should_continue(state)`:
  - If the last investigator message has no `tool_calls`, route to `"adversarial_red_team"`.
  - If `state["tool_calls"] >= budget["max_tool_calls"]`, route to `"adversarial_red_team"`.
  - Otherwise route to `"tools"`.
- `"tools"` routes through deterministic ingestion and then back to `"agent"`.
- `"adversarial_red_team"` routes to `"investment_committee"`; `"investment_committee"` routes to `END`.

## Donor code provenance

Existing adapted symbols retain provenance recorded in the execution plan. Deterministic post-tool ingestion, `ModelContextPolicy`, model-aware counting, pair-safe exchange handling, pruning/compaction helpers, and provider-capability gates are new locally written symbols and behavior; they are not copied or adapted from repositories under `reference/`. Calls to LangGraph, LangChain, tokenizer, or provider public APIs are black-box dependency use, not copied code.
