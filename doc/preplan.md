# Initial Pre-Plan — Donor Reuse and Port Map

## Decision

Do not run any donor repository as the product unchanged. Their APIs, data models, prompts, and infrastructure conflict with the narrow one-agent/local-SEC boundary.

Use installed libraries as black boxes where their existing public interface already fits: `edgartools` for SEC acquisition, `gdeltdoc` for article discovery, and `trafilatura` for article extraction. Do not copy their source.

Port small, isolated flows only where a donor already implements the exact pattern needed. Keep each port credited and tested under our contracts.

## Chosen donors and exact candidate paths

| Need | Decision | Reference path / symbol | Port scope |
| --- | --- | --- | --- |
| Outer free tool loop | Port minimal flow | `reference/ai-financial-research-agent/app/agent/graph.py` `create_financial_agent` | Keep two nodes and conditional edge shape; replace tools, prompt, state, and unwanted RAG/default-tool behavior. |
| Tool errors/logging | Port pattern | `reference/ai-financial-research-agent/app/agent/nodes.py` `create_tool_node_with_logging` | Adapt to structured recoverable tool errors and run budget. |
| Model provider seam | Port selectively | `reference/ai-financial-research-agent/app/providers/chat.py` `build_chat_model` | Use only if multi-provider support is needed in MVP; do not bring API key management/UI. |
| SEC acquisition | Black-box library | `reference/edgartools/edgar/entity/core.py` `Company` | Depend on Edgartools; build thin listing/pull adapter, never copy its SEC transport. |
| Local hybrid SEC index | Port/adapt | `reference/enterprise-agentic-rag-platform-ara/vectorstore/store.py` `build_index` | Change global paths to corpus ID paths; preserve FAISS/BM25 building. |
| Local SEC verifier entry | Port/adapt | `reference/enterprise-agentic-rag-platform-ara/app/agent.py` `ask` | Remove `web_results`, web nodes, generic chat history; return strict verification schema. |
| Provider normalization pattern | Inspect only; do not port | `reference/openbb/openbb_platform/core/openbb_core/provider/abstract/fetcher.py` `Fetcher` | Its transform-query/extract/transform separation is the right conceptual seam, but OpenBB is AGPL-3.0. Do not copy code, install its runtime, or inherit its plugin system. |
| Company research data | Black-box library | `reference/yfinance/yfinance/ticker.py` `Ticker` | Use the installed `yfinance` package later behind one `get_company_research` tool. Normalize estimates, analyst changes, financial statements, and as-of/provenance fields; never expose its many methods to the outer agent. |
| Optional company-data fallback | Black-box library, deferred | `reference/alpha_vantage/alpha_vantage/alphaintelligence.py` `AlphaIntelligence.get_news_sentiment` | Alpha Vantage is a future free-key fallback only after a real endpoint/limit smoke test; do not add it to MVP dependencies yet. |
| GDELT discovery client | Black-box library | `reference/gdelt-doc-api/gdeltdoc/api_client.py` `GdeltDoc.article_search` | Use the package later behind the existing `search_articles` tool; normalize its DataFrame output and retain source/publisher metadata. |
| Investment reasoning lenses | Prompt-only donor | `reference/ai-hedge-fund/hedge_fund/signals/buffett.py` and `lynch.py` `get_system_prompt` | Extract questions/lenses into one forensic skill; copy no multi-agent pipeline, signals, portfolio, broker, or backtest code. |
| Reddit ingestion | Selective later port | `reference/reddit-stock-ai-agent-recommendation/stock_ai/reddit/reddit_scraper.py` `RedditScraper.scrape` | Keep source retrieval mechanics only; discard its agents and Discord delivery. |
| Yahoo snapshot | Selective later port | `reference/reddit-stock-ai-agent-recommendation/stock_ai/yahoo_finance/yahoo_finance_client.py` `YahooFinanceClient.get_yf_snapshot` | Adapt output to market contract; no recommendation workflow. |
| Social trends | Inspect then port metrics | `reference/reddit-trends/` | Candidate only; retain normalized social contract, not its app. |
| Market provider abstraction | Port interface idea | `reference/stock-market-intelligence/backend/app/adapters/base.py` `MarketDataProvider` | Trim to quote/history/profile; exclude scanning, ETL, cache server, forecasts. |
| Article RSS records | Selective adapter | `reference/finance-news-aggregator/finnews/article.py` `NewsArticle`, `NewsFeed.filter` | Map records to `ArticleSearchResult`; keep publisher details internal. |
| Article discovery/extraction | Black-box packages | `gdeltdoc`; `trafilatura` | Install and wrap public APIs; no source copy. |
| Skill layout | Adopt pattern | `reference/financial-research-workshop/agents/deep_agent/skills/` | Write one project-specific Markdown skill, not donor content wholesale. |

## Explicit non-reuse

- `ai-hedge-fund` orchestration, persona agents, trading, brokers, backtesting, portfolio, and signal blending.
- `AI-Financial-Research-Agent` FastAPI API, frontend, SQL/Redis stores, routing tiers, private-database tool, evaluation service, and default financial prompts.
- Enterprise RAG web search/corrective web fallback, generic PDF-only ingestion assumptions, and external API surface.
- OpenBB provider/runtime code and plugin architecture. Its AGPL-3.0 license is incompatible with copying it into this project unless the whole distributed application adopts its terms.
- Donor UI, background workers, Discord, continuous scrapers, global data stores, and provider-specific public agent tools.

## Implementation order when coding is authorized

1. Create contracts/state and tests from `mvp-spec.md`.
2. Add Edgartools listing/pull adapter and case-local file store.
3. Adapt local hybrid retrieval and enforce no-network verifier test.
4. Add social, articles, market, and web adapters behind contracts.
5. Port tiny outer graph, forensic skill, budgets, and memo rendering.
6. Add optional Faceless script adapter after research workflow passes fixtures.
