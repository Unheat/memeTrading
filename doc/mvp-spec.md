# MVP Specification — Meme Market Forensic Research

## Status

Draft architecture specification. No application code is authorized by this document.

## Donor code provenance policy

This architecture document does not itself copy donor code. Every production module spec must identify copied or adapted donor symbols by exact `reference/<repo>/<path>:line-line` location before implementation. Ordinary library/API use is recorded as a black-box dependency instead.

## Goal

Given a ticker or unusual social signal, produce a case-local forensic memo that separates hype, professional interpretation, primary-source facts, and SEC-supported facts. The system is research-only: no portfolio construction, backtesting, trading advice, or order execution.

## Required behavior

1. One outer agent runs a free tool-calling loop: observe evidence, identify the uncertainty most likely to change its conclusion, choose a tool, update state, repeat, or finish.
2. The outer agent may use social, professional articles, general web/primary sources, market data, and SEC tools in any useful order.
3. Social material is hypothesis evidence, not authoritative proof.
4. Professional articles provide attributable human analysis; the agent compares them with other sources rather than treating them as facts.
5. Material company claims, contracts, financing, dilution, warrants, and insider activity are tested through the SEC verifier when case-local filings can answer them.
6. The SEC verifier searches only a supplied local corpus. It cannot call any network, article, social, download, company-selection, or ticker-switching capability.
7. The result records uncertainty and source provenance; unavailable or paywalled article text must be reported, never bypassed.
8. Every run begins with a `ResearchRequest` that preserves the originating user direction, optional research scope, time boundary, and budget. The outer agent may choose its next tool but may not silently broaden that direction.

## Invocation modes and scheduled delivery

The interactive caller passes a user's `ResearchRequest` to the shared research runner. A future daily scheduler is not a second agent or pipeline: it constructs the same request schema from a versioned, fixed prompt template and date, invokes the same runner, then publishes only completed artifacts to the static site.

The scheduler may select a configured universe, mandate, budget, and publication threshold, but it does not choose tools, research facts, citations, verdicts, or video claims. The short-video renderer consumes the completed memo/script only. The runner remains usable by an interactive user or another application with no scheduler or website installed. A daily run with insufficient evidence emits an explicit no-material-finding artifact rather than manufacturing a thesis.

## Outer-agent contract

The agent receives exactly these tools in MVP:

| Tool | Required input | Output contract |
| --- | --- | --- |
| `search_social` | query/ticker/time window | normalized posts, representative samples, trend metrics, source links |
| `search_articles` | query; optional ticker/sources/days/limit | normalized article records with title, publisher, time, URL, summary/metadata, access status |
| `read_article` | URL | cleaned text/metadata or explicit unavailable/paywalled/extraction-failed status |
| `search_web` | query; optional domains | primary/general-web result records |
| `get_market_data` | ticker; optional period and benchmark | normalized quote/OHLCV/history plus compact market context: multi-horizon returns, 20-day volume ratio, benchmark-relative return, 50/200-day SMA trend status, 14-day volatility, provenance, as-of time, and calculation status |
| `list_sec_filings` | ticker; optional forms/since | filing metadata and available exhibit metadata only |
| `pull_sec_filings` | case ID and exact filing/accession/document selections returned by `list_sec_filings` | `corpus_id`, downloaded documents, accessions, and local paths |
| `verify_sec_claim` | `corpus_id`, claim | verdict, confidence, cited evidence for/against, missing evidence, suggested document types |

The outer-loop state minimally holds ticker/company/CIK, trigger, root claims, evidence, contradictions, unresolved questions, searched queries, corpus IDs, tool-call count, budget state, and final status. For a catalyst investigation it also records the causal chain `signal -> demand or bottleneck -> beneficiary -> financial mechanism -> expectation gap`, the market-context result, thesis breakers, and refresh conditions. It ends when major catalyst and material risk questions are resolved, evidence is unavailable, or repeated calls have no material information gain.

## Market-context tool policy

`get_market_data` is the only technical/price-context tool in MVP. It uses historical daily OHLCV data from `yfinance` first and calculates a deliberately small, transparent set locally: 1-day, 5-day, 1-month, and 3-month returns; current volume divided by the 20-trading-day average; return relative to a declared benchmark; whether price is above or below the 50-day and 200-day SMA; and 14-day ATR or an explicit unavailable status.

The outer agent calls it only to answer a research uncertainty such as “has this catalyst already been repriced?” or “is the move company-specific rather than sector-wide?” It must describe the result as market context, never as proof of a business claim, a forecast, or a buy/sell instruction. RSI, MACD, Bollinger Bands, support/resistance, options data, short-interest strategy, backtesting, and automatic trading signals are excluded from MVP. A later per-file spec may add one only after a concrete research use case and data-quality test justify it.

## Deferred general-equity research extension

After the SEC-local RAG path is complete and tested, the same outer agent may support user-directed company or theme research such as “find public AI companies with a specified valuation profile.” This extends the outer tool list; it does not add another outer agent or change the SEC verifier boundary.

The first deferred tool is:

| Tool | Required input | Output contract |
| --- | --- | --- |
| `get_company_research` | ticker | normalized analyst targets/revisions, earnings and revenue estimates, selected financial-statement facts, earnings-calendar data, source URLs/provider names, as-of times, availability, and reliability notes |

`get_company_research` uses `yfinance` first behind the tool boundary. Its data is secondary research data, not authoritative proof: unavailable values and provider freshness are returned explicitly. Alpha Vantage is only an optional fallback after a real free-tier endpoint and rate-limit test proves a needed gap. `get_macro_data(series_ids)` is deferred until an actual macro research use case exists; FRED requires an API key and BLS is not an MVP company-research dependency.

Future tool additions must preserve source provenance. The outer agent may receive normalized fields, but every material item retains provider, source URL when available, as-of time, and reliability/availability status. SEC RAG remains restricted to downloaded SEC filings and exhibits; it never retrieves company-research, market, article, macro, or social data.

## Future capability-agent boundary

MVP has one capability-agent: `verify_sec_claim`. The outer agent owns the investigation and invokes it as a normal tool. A later capability-agent may be added only by registering one normalized tool with typed input/output, declared authority, budget/timeout, structured errors, source receipts, and uncertainty. Capability-agents cannot invoke one another, mutate outer state directly, select future outer actions, or expose provider-specific tools. No generic plugin runtime or multi-agent supervisor is authorized until a second real capability needs it.

## SEC verifier contract

Input is a claim plus one corpus ID. Output verdict is exactly `CONFIRMED`, `PARTIALLY_CONFIRMED`, `CONTRADICTED`, or `INSUFFICIENT_EVIDENCE`.

Every returned evidence item includes accession, form, filing date, document/exhibit name, exact excerpt, and SEC source URL. Suggested document types are advisory; only outer agent may call `pull_sec_filings`.

Retrieval design is case-local hybrid retrieval: BM25 plus dense FAISS results, reciprocal-rank fusion, CrossEncoder reranking, then constrained verification. The verifier has no fallback web-search node.

The SEC assessor uses OpenRouter as the initial hosted, OpenAI-compatible model provider behind a narrow adapter. It requires no Ollama runtime or locally downloaded model. The adapter sends only the claim and retrieved case-local SEC chunks; it sends no tool definitions, MCP servers, web-search capability, download capability, filing paths, or unrelated research context. This changes the verifier boundary precisely: it has no external retrieval or application tools, while the presented excerpts are intentionally sent to the approved model provider for inference. The adapter emits a JSON-schema-constrained proposed assessment and records provider, model identifier, and inference time; the verifier continues to validate every returned chunk ID and constructs SEC citations from immutable local receipts.

## Source interpretation policy

```text
social                  = what people care about; hypothesis origin
professional articles   = informed market interpretation; compare and attribute
company/counterparty    = what was announced
market context          = price/volume/relative-performance evidence; tests whether a narrative may be priced in
SEC local corpus        = forensic proof for material filing-addressable claims
```

The prompt incorporates investment lenses—customer/product value, adoption signals, disruptive-growth potential, asymmetric outcomes, permanent shareholder-loss risk, and priced-in expectations—but never creates investor-persona subagents.

## Storage and safety

Each investigation stores its JSON state, memo, SEC sources, and index under one case directory. The MVP uses filesystem storage only. Per-run caps apply to tool calls, duplicate queries, time, provider requests, and total budget. Provider failures become structured tool results so the agent can select an alternative source.

Stored state retains the originating `ResearchRequest`; scheduled artifacts also retain the fixed-template version and execution date. Static-site publication is an optional post-core delivery extension, not a separate research implementation.

## Acceptance criteria

- One compiled outer agent graph contains only `agent -> tools -> agent|end`.
- All eight outer tools conform to the contracts above; no provider-specific tool is exposed.
- SEC verifier can be tested with networking disabled and still returns local-corpus results.
- Paywalled article content is not bypassed.
- Memo distinguishes source classes and includes SEC receipt fields for each SEC assertion.
- Market-context output labels every raw and calculated field with provider, as-of time, lookback/benchmark where applicable, and availability; it cannot produce an investment action.
- Interactive and scheduled runs invoke the same research runner and produce the same evidence/citation contract; the scheduler cannot bypass research or delivery boundaries.
- No V1 code implements backtests, portfolio optimization, execution, specialist agents, article RAG, or fine-tuning.
- Deferred company-research tools do not begin implementation until the SEC-local corpus, retrieval, and verifier slices pass their acceptance tests.
