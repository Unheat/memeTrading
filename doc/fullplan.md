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

## General Equity Research Scope & Mandate

The system is a **general-purpose public equity research agent**, not a meme-stock or penny-stock trading bot. We do not trade or speculate on meme stocks. 

1. **The Role of Social/Meme Signals**: Social media platforms (Reddit, Twitter, forums) are used solely as a **grassroots sensor** to detect real-world supply and demand bottlenecks (e.g. retail shortages of DDR5 RAM, cloud GPU wait times, pharmacy backorders for weight-loss drugs).
2. **Value-Chain Tracing**: The agent traces these grassroots demand signals up the supply chain to **real public companies** (e.g. Micron, Western Digital, TSMC, Eli Lilly)—investable public equities in general.
3. **Fundamental SEC Audit as the Real Filter**: The agent conducts a rigorous SEC execution audit (checking 10-Q/10-K gross margins, inventory drawdown, CapEx, Form 4 insider transactions, and S-3 dilution). Bad leadership that fails to raise prices or expand capacity—or that engages in dilutive financing—is rejected regardless of how strong retail demand appears.
4. **No Arbitrary Market-Cap Bias**: The agent analyzes stocks in general across all market-cap tiers (mega, large, mid, small). While low-quality penny stocks typically fail the fundamental SEC audit 99.9% of the time, the system avoids arbitrary market-cap discrimination: if a smaller company demonstrates audited execution, profitability, and clean governance, the analysis evaluates the business objectively on profitability and risk.

## Runtime architecture

The system organizes institutional deep research into an **Autonomous Multi-Stage LangGraph State Machine**:

```text
               ┌────────────────────────────────────────────────────────┐
               │ STAGE 1: STRUCTURED RESEARCH PLANNER (planner_node)    │
               │  • Pydantic structured output (ResearchPlanSchema)     │
               │  • Decomposes query into research_type, ranking_count, │
               │    candidate_entities, and primary_questions           │
               │  • Populates prioritized deterministic work_queue      │
               └───────────────────────────┬────────────────────────────┘
                                           │
                                           ▼
               ┌────────────────────────────────────────────────────────┐
               │ STAGE 2: HIGH-AGENCY EXECUTOR LOOP (executor + tools)  │
               │  • 19 Normalized Tools (Web, SEC, Quant, Sub-Agents)   │
               │  • Single, pair, or peer basket multi-asset maneuvers  │
               │  • Ingest Node: Deterministic candidate isolation      │
               │    (candidates[cid]), receipts, & work queue tracking  │
               │  • Pair-safe context policy: 1M window / 200k threshold│
               └───────────────────────────┬────────────────────────────┘
                                           │ (Loop completes / out of calls)
                                           ▼
               ┌────────────────────────────────────────────────────────┐
               │ STAGE 3: SUPERVISOR GAP REFLECTION (reflection_node)   │
               │  • Audits evidence completeness & candidate diligence  │
               │  • Gaps found? -> Injects Gap Punch-List (Max 2 rounds)│
               │  • Fast-Path Early Veto Circuit Breaker (status=vetoed)│
               │    bypasses uninvestable/fraudulent assets cleanly     │
               └───────────────────────────┬────────────────────────────┘
                                           │ (Research complete or budget reached)
                                           ▼
               ┌────────────────────────────────────────────────────────┐
               │ STAGE 4: DILIGENCE LENSES & INVESTMENT COMMITTEE       │
               │  • G1 Research Completeness Gate                       │
               │  • G2 Deterministic Forensic Accounting Gate           │
               │  • G3 Deterministic Valuation Gate (calculator.mjs)    │
               │  • G4 3:1 Asymmetric Reward-to-Risk Gate               │
               │  • CIO Deliberation & Fractional Kelly Position Sizing │
               │  • Renders Final Institutional Memo & Audit JSON       │
               └───────────────────────────┬────────────────────────────┘
                                           │
                                           v
                       Creatorberry/faceless delivery (optional)
```

The 4 core stages operate as follows:

1. **Structured Research Planner (`planner_node`)**:
   - The investigation enters at `planner_node`, which invokes the model with `ResearchPlanSchema` via structured outputs (`with_structured_output`).
   - The planner categorizes the mandate (`single_diligence`, `multi_candidate_ranking`, or `general_deep_dive`), extracts explicit target tickers, extracts user-requested ranking counts (e.g. 2 for "best 2 tech stocks"), and formulates 3 to 5 falsifiable primary sub-questions.
   - It initializes a deterministic `work_queue` of prioritized `ResearchWorkItem` objects (e.g. `evidence_tier="primary_sec"`, `evidence_tier="candidate_diligence"`), ensuring that all research mandates are tracked deterministically across turns.

2. **High-Agency Tool Execution & Ingestion (`executor_node` + `tools` + `ingest_node`)**:
   - The Lead Investigator model has full operational freedom over tool selection, sequencing, and pacing. It is not restricted to a fixed linear sequence.
   - In multi-candidate ranking or comparative analysis, the model calls `register_candidate` to allocate separate, isolated candidate workspaces (`candidates[cid]`).
   - Every tool call returns a typed envelope audited by `ingest_tool_results`:
     - Company-specific metrics, quotes, and filings are routed exclusively to the owning candidate workspace (`candidates[cid]`).
     - Global macro indicators (FRED Treasury yield curves) and market benchmarks are persisted into top-level state.
     - Completed tool receipts advance corresponding items in `work_queue` from `queued` to `completed`.
   - Context is managed dynamically via `prepare_context`: 1,000,000 token capacity with a 200,000 token watermark. Older verbose tool results are pruned into compact receipts while call-and-response pair IDs remain intact.

3. **Supervisor Gap Reflection (`reflection_node`)**:
   - When the executor turn finishes, the graph evaluates `should_continue_executor`. If tool budget remains and reflection rounds are under limit (default 2), it routes to `reflection_node`.
   - The supervisor inspects all active candidate workspaces:
     - Did every candidate receive market data and SEC financial statements?
     - Did every active candidate receive valuation modeling (`valuation`) and Red Team diligence (`diligence_dossier`)?
     - If multiple candidates are active, has `compare_candidates` been executed?
     - Are there unread discovered investor PDF decks or unresolved items in `work_queue`?
   - If actionable gaps exist, the supervisor injects a `DEEP RESEARCH GAP REFLECTION` message listing the exact missing items and routes back to `executor_node`.
   - **Fast-Path Early Veto Circuit Breaker**: If the analyst uncovers an immediate disqualifying flaw (Item 4.01 auditor resignation, SEC fraud probe, balance sheet insolvency, or 7-day earnings blackout risk), it can register `register_candidate(status="vetoed", reason="...")`. The reflection supervisor recognizes the veto, marks candidate work items as completed, and allows an immediate clean exit without forcing 10+ wasteful tool calls on toxic assets.

4. **Diligence Lenses & Investment Committee (`diligence_node`)**:
   - Evaluates the four formal institutional gates:
     - **G1 Research Completeness Gate**: Verifies required primary SEC and market context evidence exist for all non-vetoed candidates.
     - **G2 Forensic Accounting Gate**: Evaluates Beneish M-Score manipulation risk, Sloan accruals quality, and SBC dilution burden.
     - **G3 Valuation Gate**: Validates that Reverse DCF and Fair Value ranges are mathematically reproducible via the deterministic `calculator.mjs` engine.
     - **G4 Asymmetry Gate**: Mathematically enforces that the upside to Base Fair Value outweighs downside to Bear Floor by at least 3.0 to 1.
   - Runs the Chief Investment Officer deliberation and calculates Fractional Kelly position sizing in deterministic code.
   - Renders the finalized publication-grade `memo.md` and machine-readable `investigation.json`.

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

The outer agent receives ten normalized tools only. Internal provider classes are not agent tools.

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

Use `adbar/trafilatura` for URL-to-cleaned-article-text and metadata. Do not implement a generic HTML/article parser. This is live research only, not an article RAG corpus. All outbound HTTP requests must pass through strict SSRF validation (blocking private/loopback/link-local/cloud-metadata targets before and after redirects).

### `read_document`

```python
read_document(url: str, candidate_id: str | None = None, max_pages: int = 20) -> DocumentContent
```

Extracts cleaned prose, structured financial tables, and embedded links from authoritative primary documents, specifically investor presentations, slide decks, earnings press releases, whitepapers, and regulatory PDFs. It automatically harvests discovered PDF/document links and attaches extracted evidence directly to the candidate workspace.

### `search_web`

```python
search_web(query: str, domains: list[str] | None = None,
           limit: int = 10, file_type: str | None = None) -> WebSearchResult
```

One general research tool covers company/counterparty websites, IR pages, press releases, and regulatory announcements. Supports `file_type='pdf'` to discover direct presentation slide decks or quarterly report PDFs (e.g. `query='NVIDIA AI capex investor presentation', file_type='pdf'`).

### `get_market_data`

```python
get_market_data(ticker: str, period: str | None = None,
                benchmark_ticker: str = "SPY",
                candidate_id: str | None = None) -> MarketDataResult
```

This remains the one market-context tool; do not add a separate technical-analysis agent or one tool per indicator. Use a provider abstraction: Yahoo/yfinance initially, Finnhub or Stooq fallback. Return normalized price, price change, volume/history, OHLCV, market capitalization, float and shares outstanding when reliable, plus available short interest.

Deterministic code derives only the compact context set needed to assess whether a catalyst may already be priced in: 1-day, 5-day, 1-month, and 3-month returns; volume divided by its 20-trading-day average; return relative to a supplied or default sector/index benchmark (joined on common trading dates); 50-day and 200-day simple-moving-average trend status; and a 14-day volatility measure such as ATR. Each derived field declares its lookback, benchmark when applicable, calculation status, provider, and source observation timestamp (`as_of` vs `retrieved_at`). The tool never returns a buy/sell signal or treats a technical indicator as evidence of business demand.

### `get_company_research`

```python
get_company_research(ticker: str, candidate_id: str | None = None) -> CompanyResearchResult
```

One Wall Street consensus benchmark tool; do not add separate analyst, estimate, or earnings-calendar tools. Returns normalized secondary research data: analyst price-target range (low, mean, high), consensus ratings (buy/hold/sell counts and trend), forward EPS and revenue estimates with revision direction, earnings calendar and next-earnings date. Every field declares its provider, as-of timestamp, and availability status; micro-caps and companies without institutional coverage return an explicit `unavailable` status per field rather than zeros. Provider abstraction: `yfinance` first (no key required); Finnhub optional when `FINNHUB_API_KEY` is configured (see keyed free-tier provider policy). The tool never produces a recommendation; the outer agent uses it only for the expectation-gap comparison against verified ground reality and SEC evidence.

### `get_macro_context`

```python
get_macro_context(series_ids: list[str]) -> MacroContextResult
```

Fetches official macroeconomic indicators from the Federal Reserve Economic Data (FRED) API (e.g. `DGS10` for 10-year Treasury yield curve, `FEDFUNDS` for federal funds rate, `CPIAUCSL` for inflation, `UNRATE` for unemployment). Used to establish the sovereign risk-free rate, cost of capital, and macroeconomic regime.

### `get_ownership_and_insider_activity`

```python
get_ownership_and_insider_activity(ticker: str, candidate_id: str | None = None,
                                   limit: int = 20) -> InsiderActivityResult
```

Audits insider transactions (SEC Form 4) and major ownership filings (13D/13G). Deterministically parses transaction codes to rigorously distinguish discretionary open-market insider buying (Code P) and selling (Code S) from non-discretionary tax withholding (Code F) or option exercises (Code M). Prevents misinterpreting executive equity compensation vesting as insider dumping.

### `register_candidate`

```python
register_candidate(ticker: str, company: str,
                   candidate_id: str | None = None,
                   reason: str = "",
                   status: str = "discovered") -> CandidateRegistrationResult
```

Registers a discovered candidate company into the screening workspace, allocating an isolated `CandidateResearchState` (`candidates[cid]`). Also acts as the **Fast-Path Early Veto** mechanism: if an analyst uncovers an immediate disqualifying fatal flaw in an 8-K (such as Item 4.01 auditor resignation, SEC fraud probe, balance sheet insolvency, or 7-day earnings blackout), it calls `register_candidate(ticker=..., status='vetoed', reason=...)`. The reflection supervisor recognizes the early veto and permits an immediate clean exit without wasteful DCF modeling.

### `compare_candidates`

```python
compare_candidates(candidate_ids: list[str],
                   metrics: list[str] | None = None) -> CandidateComparisonResult
```

Compiles a normalized cross-company comparison matrix across registered candidates. Extracts financial metrics (gross margin %, operating margin %, revenue, CapEx, free cash flow, valuation, Reverse DCF implied growth, and asymmetry ratios) from candidate workspaces, performs fiscal period alignment checks (flagging `comparable` vs `period_mismatch`), and renders `ComparisonCard` items for the durable state and final memo.

### `evaluate_valuation`

```python
evaluate_valuation(ticker: str, candidate_id: str | None = None) -> ValuationResult
```

Executes deterministic quantitative valuation modeling via `app/valuation/calculator.mjs`. Solves for the Michael Mauboussin Reverse DCF implied growth rate ($g_{\text{implied}}$) baked into the current market price, computes intrinsic Fair Value ranges (Low / Base / High), and tests the 3:1 asymmetric reward-to-risk hurdle against verified SEC cash flows, net cash, and diluted shares.

### `conduct_candidate_diligence`

```python
conduct_candidate_diligence(ticker: str, candidate_id: str | None = None,
                           focus_questions: list[str] | None = None) -> DiligenceDossierResult
```

Spawns an isolated candidate deep diligence sub-agent with its own private context window. Evaluates:
1. Michael Mauboussin Reverse Expectations & quantitative assumptions.
2. Forensic accounting audit (Beneish M-Score manipulation risk, Sloan accruals, SBC dilution).
3. Competitive moat durability & Hamilton Helmer 7 Powers rating.
4. Deterministic DCF fair value range and implied growth rate via `calculator.mjs`.
5. Air-gapped Bull Advocate (operating leverage catalysts).
6. Hostile Bear Red Team stress-testing with minimum 4 falsifiable objections, 2 numeric kill triggers, and bear floor price.
Returns a structured `diligence_dossier` that auto-promotes into the candidate workspace.

### `investigate_sec` (Option C: High-Leverage SEC Specialist Sub-Agent)

```python
investigate_sec(ticker: str, task: str,
                form: str | None = None,
                candidate_id: str | None = None) -> SecInvestigationResult
```

Commands the specialized SEC Filing Analyst sub-agent to investigate open research questions or verify complex disclosures in official SEC EDGAR filings (10-K, 10-Q, 8-K, Form 4). Under the hood, the sub-agent:
1. Auto-resolves ticker and CIK.
2. Auto-discovers relevant filings matching `form` via `_list_sec_filings`.
3. Auto-pulls documents and material exhibits to the case-local corpus via `_pull_sec_filings` if not already cached.
4. Chunks and builds the local hybrid FAISS dense + BM25 sparse vector index.
5. Executes hybrid RAG search with Reciprocal Rank Fusion (RRF) for the most relevant sections.
6. A specialized SEC Analyst LLM reads the retrieved excerpts and synthesizes a concise, grounded research response citing exact accession numbers, filing forms, dates, and verbatim quotes.
7. Auto-ingests verified evidence quotes directly into `candidate["evidence"]` and `state["evidence"]`.

### `verify_sec_claim`

```python
verify_sec_claim(claim: str, ticker: str | None = None,
                 corpus_id: str | None = None,
                 candidate_id: str | None = None) -> SECVerificationResult
```

Tests a specific material claim or rumor from social media or news articles against official local SEC filings. Automatically resolves the candidate's local corpus directory from `ticker` (or uses `corpus_id` for backward compatibility), retrieves candidate chunks via hybrid RAG, runs the isolated claim assessor, and returns a grounded `CONFIRMED`, `CONTRADICTED`, or `INSUFFICIENT_EVIDENCE` verdict with verbatim supporting/contradicting quotes and accession citations.

### `get_sec_financials`

```python
get_sec_financials(ticker: str, periods: int = 4,
                   candidate_id: str | None = None) -> SecFinancialsResult
```

Deterministic SEC XBRL financial statement extraction tool. Extracts quarterly income statement (revenue, gross margin, operating margin), balance sheet (cash, short-term investments, total debt, inventories), and cash flows (operating cash flow, CapEx) directly from official SEC XBRL data. All extractions strictly distinguish discrete quarterly durations from cumulative YTD durations, sort periods by fiscal end-date, and preserve accounting units. Zero hallucination.

### `list_sec_filings`

```python
list_sec_filings(ticker: str, forms: list[str] | None = None,
                 since: str | None = None,
                 candidate_id: str | None = None) -> SecFilingList
```

Metadata catalog browsing tool: returns form, filing date, accession number, filing URL, and document items (e.g. 8-K Item 1.01 or Item 4.01). Useful when the Lead Investigator needs to check available filing dates or identify specific 8-K event codes.

### Low-Level SEC Corpus Plumbing Tools (`pull_sec_filings`, `search_sec_evidence`, `read_sec_evidence`)

These lower-level tools are preserved for fine-grained chunk retrieval, testing fixtures, and headless automation:
- `pull_sec_filings`: Downloads explicitly selected SEC documents using server-issued filing receipts.
- `search_sec_evidence`: Direct FAISS+BM25 hybrid search inside local filing chunks.
- `read_sec_evidence`: Reads exact filing text chunks by chunk ID.
Server session context automatically injects `case_id` so the model never has to manage filesystem paths directly.

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
    messages: Annotated[Sequence[BaseMessage], add_messages]
    case_id: str
    ticker: str
    company: str | None
    cik: str | None
    trigger: dict[str, Any]
    root_claims: list[str]
    evidence: list[dict[str, Any]]
    contradictions: list[dict[str, Any]]
    unresolved_questions: list[str]
    sec_corpora: list[str]
    searches_performed: list[dict[str, Any]]
    confidence: float | None
    tool_calls: int
    status: str
    causal_chain: dict[str, str] | None
    market_context: dict[str, Any] | None
    consensus_snapshot: dict[str, Any] | None
    expectation_gap: dict[str, Any] | None
    thesis_breakers: list[str]
    adversarial_report: Any | None
    bull_report: Any | None
    forensic_report: dict[str, Any]
    quant_report: dict[str, Any]
    thematic_report: dict[str, Any]
    sector_report: dict[str, Any]
    moat_report: dict[str, Any]
    ic_verdict: Any | None
    budget_state: dict[str, Any]
    research_plan: list[dict[str, Any]]
    research_intent: dict[str, Any]
    work_queue: list[dict[str, Any]]
    candidates: dict[str, Any]
    comparisons: list[dict[str, Any]]
    source_records: list[dict[str, Any]]
    claim_records: list[dict[str, Any]]
    evidence_gate: dict[str, Any]
    accounting_gate: dict[str, Any]
    valuation_gate: dict[str, Any]
    asymmetry_gate: dict[str, Any]
```

### Two-Tier State Architecture

1. **Tier 1 (Ephemeral Conversational Working Set)**: `messages` contains the raw multi-turn dialogue with LangGraph `add_messages`. Before each model invocation, `prepare_context()` applies `ModelContextPolicy`:
   - Configurable for 1M-token windows (default `context_window_tokens=1,000,000`).
   - High activation threshold (`compact_threshold_tokens=200,000`), preserving full raw history during normal multi-turn investigation.
   - Reserved output tokens (`32,000`) and input safety margin (`32,000`) ensure the model never runs out of generation budget.
   - Pair-Safe Exchange Integrity: an assistant `AIMessage` with `tool_calls` and all matching `ToolMessage` results form an indivisible conversational unit that is never split or partially truncated.
   - Deterministic Tool-Result Pruning: old oversized tool bodies (exceeding `8,000` tokens) are replaced with compact metadata envelopes (`name`, `id`, `status`, byte size, and SHA-256 digest) before dropping older conversational units.
   - Model-aware token counting uses provider hooks (`get_num_tokens_from_messages`) where available, with explicit conservative character-based fallback.
2. **Tier 2 (Permanent Structured Evidence)**: `evidence`, `contradictions`, `market_context`, `consensus_snapshot`, `sec_corpora`, `searches_performed`, and `confidence` are populated deterministically by `ingest_tool_results` at tool-return time. They are never trimmed and are injected cleanly into the dynamic system prompt every turn.

Persist readable Markdown plus structured JSON. Keep raw SEC sources and indexes per case:

```text
cases/XYZ-2026-09-01-001/
  investigation.json
  memo.md
  article.md
  faceless/
    dialogue.json
    caption.txt
  sec/
  corpus/
```

### Report Accuracy & Integrity Policy

1. **Fail-Closed Reporting**: When prices, analyst targets, bear floors, earnings dates, or SEC evidence are missing or unparseable, report them explicitly as `UNAVAILABLE` or `INSUFFICIENT_EVIDENCE`. Never substitute synthetic defaults (e.g. defaulting price to $100 or assuming +30% upside). If essential valuation or downside data is missing, the report assigns **0.0% capital allocation** and flags the uncertainty so generated reels do not assert ungrounded claims.
2. **Strict 3:1 Asymmetric Reward-to-Risk Rule**: The 3.0x threshold is a strict hurdle for a positive long recommendation:
   $$\text{Reward-to-Risk Ratio} = \frac{\text{Base Target Price} - \text{Current Price}}{\text{Current Price} - \text{Bear Downside Floor}} \ge 3.0$$
   Any ratio below 3.0x (including 2.0–2.99x) receives `VALIDATION_WATCH` (awaiting pullback) or `PASSED`, with **0.0% position sizing**.
3. **Deterministic Valuation Scenarios**: The bear floor and base target prices must be supported by explicit valuation metrics (trough P/E, EV/Sales, net debt, dilution), not raw unverified model guesses. $0 < \text{bear\_floor} < \text{current\_price}$.
4. **Clean Fallbacks Without Hallucinations**: When model generation or parsing fails in the Red Team node, memo renderer, or reel dialogue generator, record a clean failure/degraded state. Never emit canned or fake financial claims (such as pretending "10-Q confirmed gross margin expansion" when generation failed).
5. **Path & Storage Containment**: All case-local reads, corpus pulls, index building (`sec.faiss`), and artifact writes use `case_path()` to ensure files stay cleanly organized in their respective case folders.

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
11. Implement the 3-Stage Institutional Gated Pipeline (`investigator -> air_gapped_red_team -> investment_committee`) with deterministic post-tool ingestion, adaptive 1M-context management, 3:1 asymmetry hurdle, passing discipline, and Fractional Kelly position sizing. *(Complete.)*
12. Add optional media generator (`generate_media_package`) and Creatorberry/Faceless reel video execution bridge. *(Complete.)*
13. Implement core financial accuracy and reporting fixes: fail-closed gating, strict 3.0x hurdle, discrete XBRL quarter extraction, and grounded media fallback. *(Complete.)*
14. Add lightweight prompt-injection protection (XML data delimiters + fast regex sanitization for untrusted social/article text).
15. E2E verification, golden SEC claim benchmark, and static-site publication build.

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
