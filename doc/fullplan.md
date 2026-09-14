# Meme Market Forensic Research Agent — Architecture & Implementation Plan

## Product goal

Build a research and analysis system for narrative-driven public equities. It detects unusual public attention and grassroots demand signals, investigates the narrative autonomously, tests material company claims against authoritative SEC filings, audits management execution, measures the gap between ground reality and Wall Street expectations, and writes a concise evidence-backed forensic research memo. It is not an automated trading or brokerage-execution system.

The system follows a **Scuttlebutt & Expectations Investing** strategy (Philip Fisher's scuttlebutt method, Peter Lynch's ground-reality check, and Michael Mauboussin's expectations investing):

1. **Social signal discovery**: forums and social platforms (Reddit, ApeWisdom, StockTwits) reveal what consumers, developers, and retail participants suddenly care about — for example, reports that DDR5 RAM is out of stock at local retailers, cloud GPU wait times jumping, or pharmacy backorders for a new drug.
2. **Supply-chain beneficiary tracing**: the agent maps the grassroots signal to the direct public-company beneficiaries (e.g. a RAM shortage points to Micron, SanDisk, Western Digital) — real investable companies, not penny stocks.
3. **SEC execution audit**: strong demand only creates shareholder value if management executes. The agent tests, against filings, whether the company is reacting correctly: rising average selling prices and gross margins (10-Q/10-K income statement), inventory drawdown (balance sheet), CapEx expansion for capacity (cash-flow statement), binding customer contracts (8-K), and honest insider behavior (Form 4). A company with rising demand but bad leadership — no price increases, no capacity expansion, dilutive financing — fails this audit even when the demand signal is real.
4. **Wall Street expectations benchmark**: a stock price already embeds consensus expectations. The agent compares ground reality and filing evidence against analyst consensus estimates, price targets, and revision trends to compute the expectation gap: a real catalyst that Wall Street has not priced is opportunity; one already priced is risk.

Example: social posts report DDR5 RAM shortages and surging aftermarket prices. The system determines whether the attention signal is unusual, traces it to memory-industry beneficiaries, tests through SEC filings whether those companies are expanding margins and capacity, and compares the emerging reality against Wall Street consensus to establish whether the market has already priced the shortage.

```text
grassroots demand signal
  -> autonomous investigation
  -> authoritative SEC verification + execution audit
  -> Wall Street expectations comparison
  -> forensic explanation with receipts
```

## Architectural principles

- One outer market-research agent running an institutional 3-stage gated pipeline. MVP has one isolated SEC RAG capability-agent exposed as a tool; do not build a specialist-agent hierarchy.
- Deterministic code calculates/retrieves measurable facts: provider normalization, trend metrics, market statistics, consensus estimates, filing acquisition, Form 4 XML parsing, deduplication, quotas, and storage.
- Demand-shift investigations follow one standard arc: social signal -> beneficiary tracing -> SEC execution audit -> expectation-gap benchmark. The arc is a checklist of questions to resolve, never a mandatory tool sequence.
- Wall Street consensus data (estimates, targets, ratings) is secondary research context used only for the expectation-gap comparison; it is never authoritative proof of a material claim.
- One SEC RAG verifier assesses specific claims against already downloaded local documents.
- The outer agent chooses the next action from evidence; it does not follow a fixed `social -> SEC -> web -> report` sequence.
- The SEC verifier has no internet, web-search, download, ticker-switching, or investigation-expansion authority.
- Keep agent tools few. Provider details stay behind tool implementations.
- Do not begin with Neo4j, a global knowledge graph, fine-tuning, or a corpus of all EDGAR filings.

## Runtime architecture

The system organizes institutional equity research into a **3-Stage Gated Pipeline** in LangGraph:

```text
               ┌────────────────────────────────────────────────────────┐
               │ STAGE 1: FORENSIC INVESTIGATOR (Free-Loop Tool Agent)  │
               │  • Selects tools dynamically to resolve uncertainties: │
               │    - search_social() / search_articles() / read_article│
               │    - search_web() / get_market_data()                  │
               │    - get_company_research() / get_sec_financials()     │
               │    - list_sec_filings() / pull_sec_filings()           │
               │    - verify_sec_claim() [Isolated local RAG]           │
               │  • Pre-trade gates: ADDV >= $5M & Earnings > 7d        │
               │  • Outputs: Grounded evidence list + draft thesis      │
               └───────────────────────────┬────────────────────────────┘
                                           │ (Facts passed forward)
                                           ▼
               ┌────────────────────────────────────────────────────────┐
               │ STAGE 2: AIR-GAPPED ADVERSARIAL RED TEAM               │
               │  • Hostile Short-Seller Mandate (Muddy Waters mindset) │
               │  • Zero visibility into Stage 1 bullish draft          │
               │  • Formulates: 4 Falsifiable Objections                │
               │  • Sets: 2 Quantitative Numeric Kill Triggers          │
               └───────────────────────────┬────────────────────────────┘
                                           │ (Bull Thesis + Bear Attack)
                                           ▼
               ┌────────────────────────────────────────────────────────┐
               │ STAGE 3: INVESTMENT COMMITTEE (CIO Allocation & Sizing)│
               │  • Weighs Bull Thesis against Adversarial Red Team     │
               │  • Enforces 3:1 Asymmetric Reward-to-Risk Hurdle       │
               │  • Enforces Passing Discipline (saying NO to bad traps)│
               │  • Computes Fractional Kelly Position Size (in code)   │
               │  • Renders Final Institutional Memo & Audit JSON       │
               └───────────────────────────┬────────────────────────────┘
                                           │
                                           v
                       Creatorberry/faceless delivery (optional)
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

### Scuttlebutt and expectations methodology

For demand-shift and leading-indicator investigations the agent applies three institutional lenses in addition to forensic verification:

1. **Scuttlebutt ground-reality check (Philip Fisher / Peter Lynch)**: trace the grassroots signal (consumer complaints, developer chatter, retail stockouts, wait times) to the direct public-company beneficiaries. A RAM shortage points to memory makers; GPU wait times point to hyperscalers and accelerator vendors. The beneficiary may be several steps removed from where the signal originated.
2. **Management-execution audit**: rising demand creates shareholder value only if leadership converts it into pricing power and capacity. Compare the signal against income-statement trajectory (average selling prices, gross margin expansion), balance-sheet inventory drawdown, cash-flow CapEx deployment for capacity, and financing behavior. A company with real demand but no price increases, no capacity expansion, or dilutive financing fails the audit even though the signal is genuine.
3. **Expectation-gap benchmark (Michael Mauboussin)**: a price already embeds consensus expectations. Call `get_company_research` to read what Wall Street currently models (consensus EPS/revenue estimates, price-target range, revision trend, ratings) and compare it against the verified ground reality and filing evidence. A real catalyst Wall Street has not priced is the opportunity; the same catalyst already priced is risk.

The five-step causal chain remains the audit spine: `signal -> demand or bottleneck -> beneficiary -> financial mechanism -> expectation gap`. The expectation-gap step is now explicitly benchmarked against Wall Street consensus rather than judged only from price action.

### Invocation and automation boundary

Every investigation starts from one `ResearchRequest`: the user's natural-language direction plus optional ticker, company, theme, mandate, time boundary, and budget. The request is the outer agent's direction; the agent explores freely only within that direction and its declared tool/safety limits.

Interactive use passes the user's request directly to the shared research runner. A future daily automation is only a caller: it creates the same dated `ResearchRequest` from a fixed, versioned prompt template (for example, a `catalyst_nowcast` request for a declared universe), calls that same runner, then saves the finished memo/reel script and triggers the static-site publication build. It does not contain research logic, choose tools, alter claims, generate citations, or use a separate “daily agent.” Anyone cloning the project can call the same runner interactively without the scheduler or website.

## Outer-agent tools

The MVP model receives nine tools only. Internal provider classes are not agent tools.

### `search_social`

```python
search_social(query: str | None = None, ticker: str | None = None,
              time_window: str | None = None) -> SocialSearchResult
```

MVP providers: Reddit, ApeWisdom, and StockTwits. Reddit and ApeWisdom were the first two; StockTwits was added from the `HalcyonVector/Stock-Market-Intelligence` donor adapter (unauthenticated public symbol stream, bullish/bearish tags, rate-limit-safe). X/Twitter is optional on-demand through the keyed Apify adapter (see keyed free-tier provider policy below), never a continuous firehose. Instagram, TikTok, Discord, and Telegram are not MVP dependencies.

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

### `get_company_research`

```python
get_company_research(ticker: str) -> CompanyResearchResult
```

One Wall Street consensus benchmark tool; do not add separate analyst, estimate, or earnings-calendar tools. Returns normalized secondary research data: analyst price-target range (low, mean, high), consensus ratings (buy/hold/sell counts and trend), forward EPS and revenue estimates with revision direction, earnings calendar and next-earnings date. Every field declares its provider, as-of timestamp, and availability status; micro-caps and companies without institutional coverage return an explicit `unavailable` status per field rather than zeros. Provider abstraction: `yfinance` first (no key required); Finnhub optional when `FINNHUB_API_KEY` is configured (see keyed free-tier provider policy). The tool never produces a recommendation; the outer agent uses it only for the expectation-gap comparison against verified ground reality and SEC evidence.

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

### Keyed free-tier provider policy

The system must run fully keyless: every default provider (Reddit PRAW, ApeWisdom, StockTwits, DuckDuckGo, RSS/GDELT, edgartools, yfinance) works without any account. Three keyed providers are approved as optional enhancements with graceful degradation. Each is a black-box HTTPS API dependency recorded in the dependency boundary — no repository clone and no donor code copying. A missing, invalid, or rate-limited key degrades that provider only; it must never crash the research loop or fail the run.

1. **Finnhub** (`FINNHUB_API_KEY`; free tier 60 requests/minute): structured insider transactions (pre-parsed Form 4 transaction codes and net share changes) and analyst consensus/revision data. Used by `get_company_research` as an optional provider and as a structured Form 4 supplement to the verifier's local corpus; yfinance and local RAG remain the keyless defaults.
2. **Apify** (`APIFY_API_TOKEN`; recurring free credit): on-demand Twitter/X cashtag search through hosted scraper actors when the agent needs X specifically. Results map into normalized `SocialPost` records with `source="twitter"`. Absent token means social search covers Reddit, ApeWisdom, and StockTwits only.
3. **FRED** (`FRED_API_KEY`; free tier 120 requests/minute): macro series (10-year Treasury yield, semiconductor PPI, credit spreads) read only when a research question genuinely needs macro context, such as rate-sensitive demand or cyclical capacity analysis.

Rejected keyed providers (do not add): Alpha Vantage (25 requests/day is unusable for an agent loop), Financial Modeling Prep (250 requests/day duplicates what edgartools already provides keylessly from official SEC XBRL).

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
    consensus_snapshot: dict[str, object] | None
    expectation_gap: dict[str, object] | None
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

For demand-shift investigations the memo adds a **Wall Street Expectations vs Ground Reality** section: a consensus variance table (metric, ground-reality finding, consensus estimate, gap) in the `earnings-summary` format, followed by an expectation-gap verdict stating whether the verified catalyst is unpriced, fairly priced, or already over-priced relative to consensus. The memo opens in the `investor-note` institutional format: a headline of at most 15 words, a bottom-line paragraph, core drivers, and an explicit risks/what-we-are-watching list, before the detailed forensic sections.

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

The skill incorporates the Scuttlebutt & Expectations methodology (see Outer-agent behavior): Fisher/Lynch ground-reality tracing from signal to beneficiary, the management-execution audit against XBRL statement trajectories (margins, inventory, CapEx, financing behavior) available through edgartools, and the Mauboussin expectation-gap benchmark using `get_company_research` consensus data. It also adopts the institutional output formats from `reference/financial-research-workshop/agents/deep_agent/skills/`: the `investor-note` structure (headline of at most 15 words, bottom line up front, drivers, risks/what-we-are-watching, numbered sources) and the `earnings-summary` variance table (metric, result, consensus, year-over-year) for comparing prints and estimates against consensus.

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
11. `langchain-samples/financial-research-workshop`: methodology Markdown, simple research, tracing/evaluation, plus the `investor-note` and `earnings-summary` skill formats adopted for memo output.
12. `ranaroussi/yfinance`: company-research source for analyst targets/revisions, estimates, financial statements, and supplemental market data, used behind the normalized `get_company_research` tool; provider output is secondary research data and retains provenance/as-of fields.
13. `alex9smith/gdelt-doc-api`: future package donor for the already planned GDELT article-discovery adapter; use behind `search_articles` only.
14. `RomelTorres/alpha_vantage`: future optional free-key source for company news/sentiment and transcripts only after endpoint coverage and free-tier limits are smoke-tested; do not make it an MVP dependency.
15. `OpenBB-finance/OpenBB`: inspected only for provider-standardization ideas. Do not copy, install, or run its provider/plugin runtime: its repository is AGPL-3.0 and materially broader than this product.
16. `HalcyonVector/Stock-Market-Intelligence`: selective market-context donor. Its `backend/app/services/technicals.py` contains small deterministic SMA, EMA, RSI, MACD, Bollinger Band, and ATR calculations (SMA and ATR already ported), while `backend/app/adapters/sentiment_live.py` supplied the StockTwits symbol-stream adapter adapted into `app/social/providers/stocktwits.py` (unauthenticated stream, null-body and `entities: null` guards retained). Do not inherit its web UI, API, scoring, forecasting, backtesting, portfolio, caching, or background-ingestion architecture.
17. `Creatorberry/faceless`: source-script-to-reel workflow only.

Keyed API providers — Finnhub, Apify, and FRED — are black-box HTTPS API dependencies, not repository donors: no clone, no copied code; their use is recorded in the dependency boundary per the Donor Code Provenance policy.

`jadchaar/sec-edgar-downloader` is fallback-only. `LoneRanger-dev/qa-forge` is private, inspiration only. Existing `sec-edgar-agentkit` and `gpt-researcher` are optional later donors; they do not dictate architecture.

## MVP order

1. Inspect donors; write component/reuse/licensing/compatibility map. *(Complete.)*
2. Define schemas, case storage, contracts, methodology, state/control tests. *(Complete.)*
3. Implement `list_sec_filings` and `pull_sec_filings` with Edgartools and case-local sources. *(Complete.)*
4. Build case-local ingestion/retrieval/`verify_sec_claim`; test the verifier has no external retrieval or application-tool path, while allowing its approved inference-provider call. *(Complete, including the OpenAI-compatible assessor.)*
5. Add normalized Reddit/ApeWisdom plus deterministic metrics. *(Complete; StockTwits added later from the Stock-Market-Intelligence donor.)*
6. Add normalized professional article search/read tools with RSS/GDELT/Trafilatura, paywall-safe behavior, and provider failure handling. *(Complete.)*
7. Add market and general-web adapters with provider failure handling. *(Complete: `get_market_data`, `search_web`.)*
8. Build smallest outer-agent loop, budgets, deduplication, memo renderer. *(Complete: LangGraph loop, two-tier state, tool registry with duplicate guard, `memo.md` + `investigation.json` runner.)*
9. Implement `get_company_research` (yfinance first, Finnhub optional) and upgrade prompt/memo with Scuttlebutt & Expectations framework. *(Complete: 9th tool, consensus variance table, investor-note opening.)*
10. Add real-money safeguards and deterministic SEC XBRL financials tool (`get_sec_financials` as 10th tool, 20d ADDV liquidity filter, market cap tiering, earnings blackout guard, capital safety scorecard). *(Complete.)*
11. Implement the 3-Stage Institutional Gated Pipeline (`investigator -> air_gapped_red_team -> investment_committee`) with 3:1 asymmetry hurdle, passing discipline, and Fractional Kelly position sizing.
12. Test fixture cases and failures: acquisition, verdict, stopping, provider degradation, full multi-turn scenario.
13. Add optional reel-script/Faceless layer.
14. After the interactive runner and artifact contracts are stable, add the optional daily `ResearchRequest` wrapper plus static-site publication. Reuse the runner; do not create a parallel research pipeline.

## Post-MVP Extension: Headless Subscription-Backed Execution

For users running the system who wish to use their flat-rate ChatGPT or Claude Pro/Team subscription instead of paying per-token API bills:
- **Claude Code Headless Execution**: Call `claude -p --bare --append-system-prompt-file <path> --output-format json --allowedTools all` connected to our local stdio MCP server.
- **OpenAI Codex CLI Headless Execution**: Call `codex exec --output-schema <file> --full-auto --ephemeral` connected to our local stdio MCP server.
- Both modes allow running full institutional research investigations using flat subscription allowances with zero per-token cost, while preserving our exact system charter prompts and JSON schema constraints. The standalone raw API runner (`app/agent/runner.py`) remains the default core engine for headless automation.

## Explicit V1 exclusions

- Specialist-agent hierarchies, bull/bear debates, separate news/social/SEC-download agents.
- Knowledge graphs, Neo4j, global SEC RAG, fine-tuning, portfolio optimization, prediction models, broker execution.
- Backtesting, article RAG, and invented model-only financial analysis when reputable current professional analysis is available.
- Every-EDGAR ingestion; outer agent controls pulls.
- Instagram, TikTok, Discord, Telegram; continuous X firehose (keyed on-demand Apify X search is permitted; a continuous feed is not).
- Keyed providers as hard dependencies: Finnhub, Apify, and FRED are optional with keyless fallback; the system must run with zero API keys.
- Video coupled to research internals.

## Implementation-start acceptance criteria

- Every donor has documented reuse, license, dependencies, adaptation, exclusion, and compatibility assessment.
- MVP has one outer agent and one case-local SEC verifier capability-agent; later capability-agents must appear as normalized tools under the extension boundary, never as a specialist-agent hierarchy.
- Professional article search and article reading are normalized live tools; publishers are not separate agent tools.
- Tool contracts and case-local storage are agreed.
- Verifier network isolation has a testable boundary.
- MVP excludes execution and multi-agent expansion.
