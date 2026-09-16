# Module Spec — `app/agent/tools.py` and `app/agent/graph.py`

## Responsibility

Define the complete LangChain tool registry, duplicate suppression, deterministic tool-result ownership, context-safe model invocation, deep evidence-gap reflection, and one bounded StateGraph for every research prompt.

## Tool registry

`create_agent_tools(cases_root)` returns these 17 model-visible tools:

1. `search_social`: Social chatter and hype velocity.
2. `search_articles`: Curated financial news and GDELT articles.
3. `read_article`: Clean prose extraction from news articles via Trafilatura.
4. `read_document`: Primary document reader supporting PDF presentations/reports (via `pdfplumber`) and HTML document/PDF link harvesting (via `BeautifulSoup`).
5. `search_web`: Broad web search via DuckDuckGo, supporting `file_type='pdf'` for direct document discovery.
6. `get_market_data`: Live market price, volume ratio, ATR, and liquidity context.
7. `get_company_research`: Wall Street consensus EPS/revenue estimates and price targets.
8. `list_sec_filings`: Official EDGAR metadata filing discovery (10-K, 10-Q, 8-K, Form 4).
9. `pull_sec_filings`: Download selected filings into local case corpus.
10. `search_sec_evidence`: Exploratory hybrid FAISS dense + BM25 sparse + RRF search in local SEC chunks.
11. `read_sec_evidence`: Read exact filing chunks with preceding and following context.
12. `verify_sec_claim`: Ground key factual assertions against local SEC filings.
13. `get_sec_financials`: Deterministic XBRL metrics (gross margin %, inventory QoQ change, net cash, capex).
14. `get_ownership_and_insider_activity`: Audit Form 4 insider transactions, isolating open-market buys/sales from tax withholding.
15. `get_macro_context`: Pull official macroeconomic indicators from FRED (e.g. DGS10, FEDFUNDS, CPIAUCSL).
16. `register_candidate`: Register a discovered candidate company for isolated research tracking.
17. `compare_candidates`: Generate normalized cross-company comparison cards across registered candidates.

`ToolCallGuard` suppresses repeated identical signatures within a run. Tool exceptions become structured error payloads so the agent can adapt without crashing the graph.

## One graph with deep gap reflection

`create_research_graph()` always compiles:

```text
agent → tools → deterministic ingestion → agent
  │                                         │
  │                                    (no calls & gaps)
  │                                         ↓
  │                                      reflect
  │                                         │
  │                                  (loop to agent)
  ↓
evidence completion (G1)
  └→ explicit named-company allocation request only: G1 → G2 → G3 → G4 → committee
```

The agent node receives `build_research_system_prompt`, context-compacts complete tool exchanges, binds the 17-tool registry, and clips calls to the remaining budget.

When the model returns text without tool calls, `should_continue` checks `_has_evidence_gaps(state)`. If candidates lack market/SEC data, if comparisons are missing, or if discovered PDF links have not been read, it routes to `reflect`, which injects a targeted gap-reflection prompt and loops back to `agent` to drive deeper rounds of tool calls.

## Donor code provenance

| Local symbol | Reuse type | Exact donor location | Deliberate changes |
| --- | --- | --- | --- |
| Bounded LangGraph tool-loop shape | adapted | `reference/ai-financial-research-agent/app/agent/graph.py:68-92,129-225`, tool-loop graph | Local implementation unifies all prompts, adds intent, receipts, candidate isolation, budget clipping, context policy, and gated investment extension. |
| Gap reflection loop | adapted | `reference/gpt-researcher/gpt_researcher/skills/deep_research.py:346-378`, follow-up reflection | Local state-driven evidence gap detection triggers targeted reflection turns without recursive branch nesting. |
| Document reader & link harvest | adapted | `reference/gpt-researcher/gpt_researcher/scraper/beautiful_soup/beautiful_soup.py:30-56`, HTML cleaning & link extraction | Combines `pdfplumber` tables with `BeautifulSoup` document link harvesting and `trafilatura` prose extraction. |
| Tool APIs | black-box dependency use | LangChain/LangGraph public APIs | No donor source copied. |
| Deterministic tool ingestion | locally written | N/A | Local payload parsing, receipt audit data, and candidate ownership enforcement. |
