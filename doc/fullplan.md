# Meme Market Forensic Research Agent — Architecture & Implementation Plan

## Product goal

Build a research and analysis system for noisy, meme-driven equities. It detects unusual public attention, investigates a narrative autonomously, tests material company claims against authoritative SEC filings, and writes a concise evidence-backed forensic memo. It is not an automated trading or brokerage-execution system.

Example: social posts say `$XYZ signed a $500M Nvidia partnership and is going to squeeze.` The system determines whether attention is unusual, traces the claim, tests company and counterparty evidence, establishes whether an agreement is binding and its value real, then assesses financing, dilution, warrant, and insider-risk evidence.

```text
noisy market narrative
  -> autonomous investigation
  -> authoritative SEC verification
  -> forensic explanation with receipts
```

## Architectural principles

- One outer market-research agent. MVP has one isolated SEC RAG capability-agent exposed as a tool; do not build a specialist-agent hierarchy.
- Deterministic code calculates/retrieves measurable facts: provider normalization, trend metrics, market statistics, filing acquisition, Form 4 XML parsing, deduplication, quotas, and storage.
- One SEC RAG verifier assesses specific claims against already downloaded local documents.
- The outer agent chooses the next action from evidence; it does not follow a fixed `social -> SEC -> web -> report` sequence.
- The SEC verifier has no internet, web-search, download, ticker-switching, or investigation-expansion authority.
- Keep agent tools few. Provider details stay behind tool implementations.
- Do not begin with Neo4j, a global knowledge graph, fine-tuning, or a corpus of all EDGAR filings.

## Runtime architecture

```text
                         OUTER MARKET AGENT
                    free model / tool-calling loop
                 chooses largest remaining uncertainty
                                   |
          +------------------------+-----------------------+
          |                        |                       |
          v                        v                       v
   search_social()         search_articles()      get_market_data()
 Reddit, ApeWisdom,        professional news,      Yahoo / fallback
 Bluesky optional          analyst commentary
          |                        |                       |
          +------------------------+-----------------------+
                                   |
                    read_article() / search_web()
                 cleaned articles / primary sources
                                   |
                                   |
                            claim discovered
                                   |
                                   v
                         list_sec_filings()
                           metadata only
                                   |
                                   v
                         pull_sec_filings()
                    outer agent chooses documents
                    writes case-local corpus
                                   |
                                   v
                         SEC RAG VERIFIER
             local corpus only; no network or downloads
                                   |
           CONFIRMED | PARTIALLY_CONFIRMED | CONTRADICTED |
                        INSUFFICIENT_EVIDENCE
                                   |
                                   v
                         OUTER MARKET AGENT
                    research more, pull more, or finish
                                   |
                                   v
                   forensic memo, optional short reel script
                                   |
                                   v
                       Creatorberry/faceless delivery
```

### Outer-agent behavior

At every turn ask: **What unresolved question would most materially change the current thesis?** Update explicit state, select useful tool, interpret result, then continue until material questions are resolved, reliable evidence is unavailable, or calls stop yielding information.

Social creates hypotheses; it never proves material claims. Professional articles and analyst commentary show what informed market participants already think; leverage their analysis, then independently test material factual claims. Evidence priority:

1. SEC and other regulatory filings.
2. Government/regulatory sources.
3. Company and counterparty primary sources.
4. Reputable financial reporting and analyst commentary.
5. Industry publications.
6. Social media.

Actively seek contradiction. For example: detect `XYZ` on Reddit, read professional coverage, examine primary sources, pull an 8-K plus exhibits, ask whether the agreement is binding, then trace the claimed $500M origin if filing evidence does not establish it. The agent may return to social, articles, or web research after SEC verification.

### Invocation and automation boundary

Every investigation starts from one `ResearchRequest`: the user's natural-language direction plus optional ticker, company, theme, mandate, time boundary, and budget. The request is the outer agent's direction; the agent explores freely only within that direction and its declared tool/safety limits.

Interactive use passes the user's request directly to the shared research runner. A future daily automation is only a caller: it creates the same dated `ResearchRequest` from a fixed, versioned prompt template (for example, a `catalyst_nowcast` request for a declared universe), calls that same runner, then saves the finished memo/reel script and triggers the static-site publication build. It does not contain research logic, choose tools, alter claims, generate citations, or use a separate “daily agent.” Anyone cloning the project can call the same runner interactively without the scheduler or website.

## Outer-agent tools

The MVP model receives eight tools only. Internal provider classes are not agent tools.

### `search_social`

```python
search_social(query: str | None = None, ticker: str | None = None,
              time_window: str | None = None) -> SocialSearchResult
```

MVP providers: Reddit and ApeWisdom. Bluesky is optional. X is on-demand/later, not a continuous firehose. Instagram, TikTok, Discord, Telegram, and StockTwits are not MVP dependencies.

Normalize ticker, source, timestamp, text, engagement, author identifier when available, cashtags, links, representative posts, mention counts, and calculated trend features. Code calculates mention velocity, rolling baseline, z-score, unique-author ratio, engagement acceleration, duplicate/repost filtering, and mention-price divergence. The model interprets features; it does not receive thousands of raw posts or perform raw statistics.

### `search_articles`

```python
search_articles(query: str, ticker: str | None = None,
                sources: list[str] | None = None, days: int = 7,
                limit: int = 20) -> ArticleSearchResult
```

This first-class research tool finds professional financial news and analysis. Internally combine `areed1192/finance-news-aggregator` source/RSS adapters, `gdeltdoc` query-based article discovery, and optional normal web search. Prefer or restrict domains when appropriate, such as Reuters, WSJ, CNBC, and MarketWatch; results are normalized so the model never selects a provider directly. Do not expose every publisher as a separate tool.

Paywalls must not be bypassed. Preserve usable RSS headline/description metadata and seek accessible equivalent coverage when full text cannot be read.

### `read_article`

```python
read_article(url: str) -> ArticleContent
```

Use `adbar/trafilatura` for URL-to-cleaned-article-text and metadata. Do not implement a generic HTML/article parser. This is live research only, not an article RAG corpus.

### `search_web`

```python
search_web(query: str, domains: list[str] | None = None) -> WebSearchResult
```

One general research tool covers company/counterparty websites, IR pages, press releases, and regulatory announcements. Use `search_articles` for professional news and analysis. Do not add separate company, news, counterparty, article, or social agents.

### `get_market_data`

```python
get_market_data(ticker: str, period: str | None = None) -> MarketDataResult
```

This remains the one market-context tool; do not add a separate technical-analysis agent or one tool per indicator. Use a provider abstraction: Yahoo/yfinance initially, Finnhub or Stooq fallback. Return normalized price, price change, volume/history, OHLCV, market capitalization, float and shares outstanding when reliable, plus available short interest.

Deterministic code derives only the compact context set needed to assess whether a catalyst may already be priced in: 1-day, 5-day, 1-month, and 3-month returns; volume divided by its 20-trading-day average; return relative to a supplied or default sector/index benchmark; 50-day and 200-day simple-moving-average trend status; and a 14-day volatility measure such as ATR. Each derived field declares its lookback, benchmark when applicable, calculation status, provider, and as-of timestamp. The tool never returns a buy/sell signal or treats a technical indicator as evidence of business demand. RSI, MACD, and Bollinger Bands are deferred until a real research question demonstrates that the compact set is insufficient.

### `list_sec_filings`

```python
list_sec_filings(ticker: str, forms: list[str] | None = None,
                 since: str | None = None) -> SecFilingList
```

Metadata only: form, filing date, accession, filing URL, and cheaply available exhibits. No bodies download. Use a thin wrapper around `edgartools` and official SEC data; respect SEC identification and rate limits.

### `pull_sec_filings`

```python
pull_sec_filings(case_id: str,
                 selections: list[SelectedSecFiling]) -> PulledCorpus
```

`SelectedSecFiling` identifies one result returned by `list_sec_filings` by its accession and explicitly names the primary document and any material exhibits to acquire. The outer agent chooses these exact records; it does not merely supply a ticker, form filter, and arbitrary limit. Download selected filing text and material exhibits to one case-local corpus, returning `corpus_id`, document metadata, and accessions. Never indiscriminately ingest EDGAR.

### `verify_sec_claim`

```python
verify_sec_claim(corpus_id: str, claim: str) -> SECVerification
```

Verifier is a black-box local-evidence tool. Internals may use BM25, vectors, reranking, or corrective retrieval, but never a web-search fallback.

## Future capability-agent extension boundary

The SEC verifier is the first **capability-agent**, not a peer manager or a second outer loop. The outer market agent remains the sole investigation owner. A later specialized capability—such as a market-data analyst, social-pattern analyst, or counterparty-document verifier—may be added only as one new normalized outer-agent tool.

Each capability-agent must have a small explicit contract:

```text
tool name + description
typed input envelope
declared authority and data boundary
bounded execution budget/timeout
typed success result or structured recoverable error
source receipts and uncertainty fields
```

Outer-agent code builds its available tools from an explicit registry at composition time. It learns a new capability from that tool's name, description, and input/output schema; the free tool-calling loop itself is unchanged. Capability-agents may not call each other, mutate outer investigation state directly, select the next investigation action, or silently expose provider-specific tools. The outer agent passes only the narrow data needed for each call and decides whether to use its result.

Do not implement a generic plugin loader, dynamic code loading, a message bus, or a multi-agent supervisor in MVP. Add a registry entry and its contract tests only when a second real capability is approved.

## SEC verifier boundary and return contract

Verifier may query its local index, rerank, read downloaded filings/exhibits, compare passages, return exact support/contradiction, identify missing evidence, and recommend document types. It may not search web/social/news, download filings, choose a company, switch ticker, or expand an investigation.

The verifier's natural-language assessment uses a configured hosted OpenAI-compatible model provider through a narrow injected assessor seam. OpenRouter is one supported deployment choice, not a requirement. No Ollama runtime, local model download, or always-running local model server is required. The assessor receives only the claim and retrieved case-local SEC chunks, and the application sends no tool definitions, MCP servers, web-search capability, download capability, filing paths, or unrelated research context with that call. “No internet” for the verifier therefore means **no external retrieval or application tools**; the retrieved excerpts are intentionally sent to the approved model provider for inference. JSON-schema-constrained output and post-generation receipt validation are both required: schema compliance does not authorize the model to invent citations. Provider base URL, model identifier, and inference time must be recorded with the case so this data-handling boundary is auditable.

```python
class SECVerification(BaseModel):
    claim: str
    verdict: Literal["CONFIRMED", "PARTIALLY_CONFIRMED",
                     "CONTRADICTED", "INSUFFICIENT_EVIDENCE"]
    confidence: float
    explanation: str
    evidence_for: list[SecEvidence]
    evidence_against: list[SecEvidence]
    material_sec_facts: dict[str, object]
    missing_evidence: list[str]
    suggested_document_types: list[str]

class SecEvidence(BaseModel):
    accession: str
    form: str
    filing_date: str
    document: str
    quote: str
    source_url: str
```

Suggestions are recommendations only. Outer agent decides whether more documents are downloaded.

## SEC acquisition scope

Use `dgunning/edgartools` as primary acquisition library instead of writing ticker-CIK, filing, exhibit, and SEC transport plumbing. `jadchaar/sec-edgar-downloader` is narrow fallback only. Official source remains SEC EDGAR/data.sec.gov.

- Tier 1: `8-K`, `8-K/A`, relevant `EX-10.*`, `EX-4.*`, `EX-99.*`, `EX-2.*`; inspect Items 1.01, 1.02, 2.01, 2.03, 3.02, 7.01, 8.01, 9.01.
- Financing: `S-1`, `S-1/A`, `S-3`, `S-3/A`, `424B3`, `424B4`, `424B5`; ATM, shelves, offering capacity, warrants, pre-funded warrants, convertibles, resets/cashless exercise, ownership limits.
- Financial: `10-Q`, `10-Q/A`, `10-K`, `10-K/A`; cash, liquidity, going concern, debt, warrants, share count, authorized shares, subsequent events, related parties.
- Insider: `4`, `4/A`, `144`; parse Form 4 XML deterministically, preserve transaction codes/footnotes, never call any holding change “dumping” without evidence.
- Ownership: `SC 13D`, `SC 13D/A`, `SC 13G`, `SC 13G/A`. Foreign issuers: `6-K`, `20-F`, `F-1`, `F-3`.

## State, storage, and cost control

```python
class InvestigationState(TypedDict):
    ticker: str
    company: str | None
    cik: str | None
    trigger: dict[str, object]
    root_claims: list[str]
    evidence: list[dict[str, object]]
    contradictions: list[dict[str, object]]
    unresolved_questions: list[str]
    sec_corpora: list[str]
    searches_performed: list[dict[str, object]]
    confidence: float | None
    tool_calls: int
    status: str
```

Persist readable Markdown plus structured JSON. Keep raw SEC sources and indexes per case:

```text
cases/XYZ-2026-09-01-001/
  investigation.json
  memo.md
  sec/
  corpus/
```

Start filesystem-only. Add DB only when concurrent case handling proves need. Enforce max tool calls/rounds, provider limits, timeout, budget, duplicate-query detection. Track information gain: new source, claim, resolved uncertainty, contradiction, or material verdict change; stop repeated no-value calls.

Persist the originating `ResearchRequest`, rendered memo, source/citation receipts, and request-template version when scheduled. A scheduled run that cannot meet the publication threshold records an explicit no-material-finding result rather than inventing a thesis.

## Output and delivery

Memo includes trigger, hype claims, confirmed facts, contradicted/exaggerated claims, SEC evidence, dilution/financing risk, material insider activity, remaining uncertainty, source links, confidence. Every SEC claim keeps form, accession, filing date, direct source, and relevant excerpt.

Generate optional short explainer script only after memo, then send script to `Creatorberry/faceless`. Research never depends on video:

```text
forensic memo -> short reel script -> faceless -> voice/captions/video
```

The daily publication wrapper consumes only completed research artifacts. It writes dated static-site content and invokes the normal site build/deploy mechanism; it cannot add unsupported claims to a memo or video.

## Planned module boundaries

```text
app/
  agent/graph.py state.py prompts.py runner.py
  tools/social.py articles.py web.py market.py sec.py
  social/reddit.py apewisdom.py bluesky.py metrics.py
  sec/acquisition.py corpus.py indexing.py retrieval.py verifier.py schemas.py
  storage/cases.py
  api/routes.py
skills/meme_forensics/SKILL.md
cases/
tests/
reference/
```

`app/agent` owns orchestration; `tools` exposes normalized tools; `social` and `sec` hold deterministic services; `storage` owns persistence; delivery consumes completed memo only. No module may bypass verifier network isolation.

## Research methodology skill

`skills/meme_forensics/SKILL.md` directs the model to be skeptical, avoid a fixed sequence, choose the greatest unresolved uncertainty, treat social as hypothesis generation, use professional analysis as informed context rather than recreating analysis from zero, test material claims with SEC evidence when relevant, seek disagreement, avoid duplicate searches, and stop once catalyst, dilution risk, and meaningful uncertainty are assessed or reliable evidence is unavailable.

The skill also selectively adapts investment-thinking ideas from `virattt/ai-hedge-fund`: product and user-value observation, qualitative adoption/scuttlebutt, disruptive-growth potential, asymmetric upside/downside, permanent shareholder-loss risk, and whether expectations are already priced in. These are reasoning lenses for the one outer agent, not separate Buffett, Lynch, Fisher, or other persona agents.

For a leading-indicator investigation, the skill treats market context as a pricing check: it compares the trigger against the causal chain `signal -> demand or bottleneck -> beneficiary -> financial mechanism -> expectation gap`, then calls `get_market_data` when it needs to learn whether price, relative performance, volume, or trend already suggest a repricing. A social spike, SMA, RSI, or any other indicator cannot independently establish demand or a recommendation.

Research flow is conceptual, never mandatory:

```text
SOCIAL
  -> what people suddenly care about; hypotheses
PROFESSIONAL ARTICLES / ANALYST COMMENTARY
  -> informed market analysis and claims to compare
COMPANY / COUNTERPARTY PRIMARY SOURCES
  -> what was actually announced
SEC RAG
  -> local, authoritative forensic check of material claims and risks
```

## Reference repositories and inspection order

All repository donors used by the project stay unmodified in `reference/`; package-only dependencies are installed normally. They are donors or libraries, not runtime engines to run “as-is.” Before code, produce a component/reuse map for each repository donor: useful modules, license, dependencies, direct reuse, adaptation, exclusions, compatibility risks.

1. `sebtosca/AI-Financial-Research-Agent`: required outer-agent donor for small free LangGraph tool loop, state, execution, failure handling, reporting/tracing. Replace its rigid finance prompt; do not replace this outer agent with `ai-hedge-fund` multi-agent architecture.
2. `virattt/ai-hedge-fund`: strategy/prompt donor only. Extract selected investment-thinking lenses into the skill; do not run its investor persona agents.
3. `johnnychang25678/reddit-stock-ai-agent-recommendation`: PRAW, filtering, tickers, Yahoo/persistence. Flatten providers; exclude News/DD/YOLO/Stock-Picker agents.
4. `ramiNoodleCode/reddit-trends`: ApeWisdom/Reddit, history, velocity, momentum, spikes, price divergence.
5. `areed1192/finance-news-aggregator`: ready-made financial RSS/source adapters, including WSJ, CNBC, MarketWatch, Nasdaq, S&P Global, Seeking Alpha, Yahoo Finance, and CNN Finance. Normalize behind `search_articles`.
6. `gdeltdoc`: query-based cross-domain article discovery. Use it for targeted catalyst searches and preferred/restricted domains.
7. `adbar/trafilatura`: article URL extraction and metadata. Use it behind `read_article`.
8. `dgunning/edgartools`: discovery/acquisition, CIK, parsing, exhibits. Wrap, do not fork SEC plumbing.
9. `ara-5/Enterprise-Agentic-RAG-Platform`: required SEC RAG donor: BM25 plus dense embeddings/FAISS, RRF fusion, CrossEncoder reranking, verification. Remove web-search fallback completely.
10. `digit987/enterprise-agentic-rag-platform`: optional retrieval/reranking/verification ideas only; exclude unnecessary multi-agent orchestration.
11. `langchain-samples/financial-research-workshop`: methodology Markdown, simple research, tracing/evaluation.
12. `ranaroussi/yfinance`: future company-research source for analyst targets/revisions, estimates, financial statements, and supplemental market data. Use behind one normalized `get_company_research` tool; provider output is secondary research data and retains provenance/as-of fields.
13. `alex9smith/gdelt-doc-api`: future package donor for the already planned GDELT article-discovery adapter; use behind `search_articles` only.
14. `RomelTorres/alpha_vantage`: future optional free-key source for company news/sentiment and transcripts only after endpoint coverage and free-tier limits are smoke-tested; do not make it an MVP dependency.
15. `OpenBB-finance/OpenBB`: inspected only for provider-standardization ideas. Do not copy, install, or run its provider/plugin runtime: its repository is AGPL-3.0 and materially broader than this product.
16. `HalcyonVector/Stock-Market-Intelligence`: selective market-context donor. Its `backend/app/services/technicals.py` contains small deterministic SMA, EMA, RSI, MACD, Bollinger Band, and ATR calculations, while `backend/app/services/explain.py` demonstrates combining quote, candles, news, and sentiment. Port only the approved compact-market-context functions under a future per-file specification with exact provenance; do not inherit its web UI, API, scoring, forecasting, backtesting, portfolio, caching, or background-ingestion architecture.
17. `Creatorberry/faceless`: source-script-to-reel workflow only.

`jadchaar/sec-edgar-downloader` is fallback-only. `LoneRanger-dev/qa-forge` is private, inspiration only. Existing `sec-edgar-agentkit` and `gpt-researcher` are optional later donors; they do not dictate architecture.

## MVP order

1. Inspect donors; write component/reuse/licensing/compatibility map.
2. Define schemas, case storage, contracts, methodology, state/control tests.
3. Implement `list_sec_filings` and `pull_sec_filings` with Edgartools and case-local sources.
4. Build case-local ingestion/retrieval/`verify_sec_claim`; test the verifier has no external retrieval or application-tool path, while allowing its approved inference-provider call.
5. Add normalized Reddit/ApeWisdom plus deterministic metrics.
6. Add normalized professional article search/read tools with RSS/GDELT/Trafilatura, paywall-safe behavior, and provider failure handling.
7. Add market and general-web adapters with provider failure handling.
8. Build smallest outer-agent loop, budgets, deduplication, memo renderer.
9. Test fixture cases and failures: acquisition, verdict, stopping.
10. Add optional reel-script/Faceless layer.
11. After the interactive runner and artifact contracts are stable, add the optional daily `ResearchRequest` wrapper plus static-site publication. Reuse the runner; do not create a parallel research pipeline.

## Explicit V1 exclusions

- Specialist-agent hierarchies, bull/bear debates, separate news/social/SEC-download agents.
- Knowledge graphs, Neo4j, global SEC RAG, fine-tuning, portfolio optimization, prediction models, broker execution.
- Backtesting, article RAG, and invented model-only financial analysis when reputable current professional analysis is available.
- Every-EDGAR ingestion; outer agent controls pulls.
- Instagram, TikTok, Discord, Telegram, continuous X.
- StockTwits as core provider.
- Video coupled to research internals.

## Implementation-start acceptance criteria

- Every donor has documented reuse, license, dependencies, adaptation, exclusion, and compatibility assessment.
- MVP has one outer agent and one case-local SEC verifier capability-agent; later capability-agents must appear as normalized tools under the extension boundary, never as a specialist-agent hierarchy.
- Professional article search and article reading are normalized live tools; publishers are not separate agent tools.
- Tool contracts and case-local storage are agreed.
- Verifier network isolation has a testable boundary.
- MVP excludes execution and multi-agent expansion.
