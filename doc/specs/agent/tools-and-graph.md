# Module Spec — `app/agent/tools.py` and `app/agent/graph.py`

## Responsibility

Define the tool registry wrapping all 8 normalized tools for LangGraph, duplicate call containment, context trimming, and the StateGraph workflow loop.

## `app/agent/tools.py`

Exposes `create_agent_tools(cases_root: Path | None = None)` returning a list of LangChain-compatible tools:
1. `search_social(query, ticker, time_window)` -> calls `app.social.search.search_social`.
2. `search_articles(query, ticker, sources, days, limit)` -> calls `app.articles.search.search_articles`.
3. `read_article(url)` -> calls `app.articles.reader.read_article`.
4. `search_web(query, domains, limit)` -> calls `app.websearch.search.search_web`.
5. `get_market_data(ticker, period, benchmark_ticker)` -> calls `app.market.market_data.get_market_data`.
6. `list_sec_filings(ticker, forms, since)` -> calls `app.sec.acquisition.list_sec_filings`.
7. `pull_sec_filings(case_id, selections)` -> calls `app.sec.pull.pull_sec_filings`.
8. `verify_sec_claim(corpus_id, claim)` -> calls `app.sec.verifier.verify_sec_claim`.

### Duplicate Call Guard
Wraps tool execution with a call-signature hash `hash(tool_name, sorted_args)`:
- If a tool is called repeatedly with identical arguments within the same run, returns a structured note: `"[DUPLICATE_CALL] Identical query already performed. Use prior results."` rather than re-executing.
- Exceptions are trapped and returned as string error messages so the agent loop does not crash.

## `app/agent/graph.py`

### StateGraph Architecture
- Graph definition: `workflow = StateGraph(InvestigationState)`
- Nodes:
  - `"agent"`: Prepares dynamic prompt, trims message history to 4k tokens via `trim_messages`, invokes model with bound tools, increments tool call counters.
  - `"tools"`: Executes tool calls using `ToolNode` or customized safe executor.
- Conditional Edge `should_continue(state)`:
  - If last message has no `tool_calls` -> route to `END`.
  - If `state["tool_calls"] >= budget["max_tool_calls"]` -> route to `END`.
  - Otherwise -> route to `"tools"`.
- Edge from `"tools"` routes back to `"agent"`.
