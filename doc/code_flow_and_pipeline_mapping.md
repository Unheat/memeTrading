# Code Flow and Pipeline Architecture Mapping

This document provides a comprehensive, code-level guide to the deep research and valuation agent architecture. It maps every source file, class, function, and state transition in `app/agent/` (and its supporting financial, valuation, and SEC engines) directly to the stages and nodes defined in [PIPELINE_ARCHITECTURE.md](../PIPELINE_ARCHITECTURE.md).

---

## 1. Executive Reference to `PIPELINE_ARCHITECTURE.md`

The system implements an institutional-grade, multi-stage LangGraph directed acyclic graph (DAG) and state machine compiled in [`app/agent/graph.py::create_research_graph`](../app/agent/graph.py). 

The architecture strictly enforces the **Separation of Duties** principle:
- **The Analyst Workbench (Stages 1–4)**: The research agent loops dynamically through tools, sub-agents, and mathematical engines to discover candidates, ingest SEC filings, audit financial quality, run reverse DCFs, and reflect on missing evidence.
- **The Investment Committee Boardroom (Stage 5)**: A governance layer that executes zero heavy models. It evaluates deterministic mathematical gates (G1–G4) and conducts a single Chief Investment Officer (CIO) deliberation on the promoted candidate dossier.

```
                  ┌────────────────────────────────────────────────────────┐
                  │          Stage 1: Structured Planning (planner)        │
                  │              generate_research_plan()                  │
                  └──────────────────────────┬─────────────────────────────┘
                                             │
                                             ▼
                  ┌────────────────────────────────────────────────────────┐
                  │      Stage 2: Deep Research Agent Loop (executor)      │
                  │                  The Analyst (LLM)                     │
                  └──────┬───────────────────────▲─────────────────────────┘
                         │                       │
           tool_calls    │                       │ feedback / next turn
                         ▼                       │
                  ┌──────────────┐        ┌──────┴───────┐
                  │    tools     │───────▶│    ingest    │ Stage 3: Evidence Ingestion
                  │  (ToolNode)  │        │ (FactCards)  │
                  └──────────────┘        └──────────────┘
                         │
        no tool calls    │
                         ▼
                  ┌───────────────────────────────────────────────┐
                  │        Stage 4: Gap Reflection (reflect)      │
                  │   Audit state vs plan; up to 2 gap rounds     │
                  └──────┬────────────────────────────────┬───────┘
                         │                                │
           gaps found    │                                │ research complete / budget reached
                         ▼                                ▼
                  [Loop to executor]              ┌──────────────────────────────────────────┐
                                                  │ Stage 5: Final Decision & Governance     │
                                                  │             (diligence)                  │
                                                  │ • G1 Evidence Gate                       │
                                                  │ • Candidate Promotion                    │
                                                  │ • G2-G4 Accounting/Valuation/Asymmetry   │
                                                  │ • CIO Deliberation & Kelly Sizing        │
                                                  └───────────────────┬──────────────────────┘
                                                                      │
                                                                      ▼
                                                          [Final Universal Memo]
```

---

## 2. Stage-by-Stage Code & Node Correspondence

### Stage 1: Structured Planning (`planner` node)

- **Graph Node Name**: `"planner"`
- **Implementation**: `planner_node(state)` in [`app/agent/graph.py:164`](../app/agent/graph.py)
- **Primary Source Files**:
  - [`app/agent/planning.py`](../app/agent/planning.py) (`generate_research_plan`, `ResearchPlanSchema`)
  - [`app/agent/state.py`](../app/agent/state.py) (`ResearchIntent`, `ResearchRequest`)
  - [`app/agent/ledger.py`](../app/agent/ledger.py) (`ResearchWorkItem`)

#### Execution Flow
1. **Model-First Scout Assessment**: Before generating the plan, `planner_node` calls `assess_scout_need(model, query, ticker, company)` in [`app/agent/planning.py`](../app/agent/planning.py). 
   - **Fast-Path**: If the user already provided an explicit ticker or company, scouting is bypassed with zero tool calls or searches.
   - **Open-Ended Screening**: If open-ended (e.g. "find best 2 stocks in tech"), the LLM formulates 1–2 concise keyword search queries and selects the appropriate tool: `screen_stocks` (quantitative factor/preset filtering), `search_web` (general industry commentary), `search_articles` (news/earnings catalysts), or `search_social` (retail momentum).
   - **Targeted Discovery Execution**: Only the model-formulated queries are executed, extracting candidate companies, prices, and metrics into `scout_context`.
2. **Structured Plan Generation**: Calls `generate_research_plan()` in [`planning.py:110`](../app/agent/planning.py), which binds `ResearchPlanSchema` via model structured outputs (`with_structured_output`) grounded by `scout_context`. The plan identifies:
   - `research_type`: `"single_diligence"`, `"multi_candidate_ranking"`, or `"general_deep_dive"`.
   - `candidate_entities`: Explicit tickers to evaluate.
   - `primary_questions`: Specific hypotheses to test.
3. **Workspace Pre-Seeding**: The planner auto-initializes isolated candidate workspaces (`cand_{ticker}`) inside `state["candidates"]`. This ensures downstream tool calls never fail due to unseeded entity keys.
4. **Work Queue Hydration**: Translates the plan's questions and candidate tickers into prioritized `ResearchWorkItem` objects stored in `state["work_queue"]`.
5. **State Transition**: Appends the approved plan summary to `state["messages"]` and unconditionally routes to `"executor"`.

---

### Stage 2: Deep Research Agent Loop (`executor` & `tools` nodes)

- **Graph Node Names**: `"executor"` and `"tools"`
- **Router Function**: `should_continue_executor(state)` in [`app/agent/graph.py:90`](../app/agent/graph.py)
- **Primary Source Files**:
  - [`app/agent/graph.py`](../app/agent/graph.py) (`executor_node`, `should_continue_executor`)
  - [`app/agent/context.py`](../app/agent/context.py) (`ModelContextPolicy`, `prepare_context`)
  - [`app/agent/prompts.py`](../app/agent/prompts.py) (`build_research_system_prompt`)
  - [`app/agent/tools.py`](../app/agent/tools.py) (`create_agent_tools`, `ToolCallGuard`)
  - [`app/market/screener.py`](../app/market/screener.py) (`execute_equity_screen`)

#### Execution Flow
1. **Context Compaction**: `executor_node` calls `prepare_context()` from [`context.py:237`](../app/agent/context.py). This enforces pair-safe pruning: if the conversation approaches token limits, older tool message bodies are truncated into compact metadata envelopes while strictly preserving tool-call/tool-message ID pairings and entity backlinks.
2. **System Prompt Reprojection**: The system prompt is constructed via `build_research_system_prompt()` in [`prompts.py:157`](../app/agent/prompts.py). It permanently injects active `FactCard` items, candidate workspace statuses, and the research mandate under `DURABLE RESEARCH STATE`.
3. **Model Tool Invocation**: The LLM analyzes the research state and generates tool calls.
4. **Budget Admission Gate**: `executor_node` inspects `state["budget_state"]["max_tool_calls"]` (default 50). Tool calls exceeding the remaining budget are truncated.
5. **Routing via `should_continue_executor`**:
   - If pending tool calls exist $\rightarrow$ routes to `"tools"`.
   - If the LLM output plain text with no tool calls and reflection budget remains $\rightarrow$ routes to `"reflect"`.
   - If tool budgets are exhausted $\rightarrow$ bypasses directly to `"diligence"`.

---

### The Stage 2 Sub-Agent & Diligence Tool Ecosystem

In Stage 2, the LLM has access to a registry of tools. Two of these tools are autonomous sub-agents that run deep multi-turn loops:

```
                          Stage 2: Executor Tools
                                    │
       ┌────────────────────────────┼─────────────────────────────┐
       ▼                            ▼                             ▼
Discovery, Screening & Market Data  investigate_sec()           conduct_candidate_diligence()
• screen_stocks                     Autonomous SEC Analyst      Candidate Diligence Sub-Agent
• search_web                        Sub-Agent                   (diligence.py)
• get_sec_financials                (app/sec/sec_agent.py)               │
• get_market_data                                                        ▼
• register_candidate                                            1. Expectations Analyst (expectations.py)
• compare_candidates                                            2. Forensic Accounting (specialists.py)
                                                                3. Moat Analysis (specialists.py)
                                                                4. Quant DCF Engine (specialists.py)
                                                                5. Bull Advocate (bull.py)
                                                                6. Bear Red Team (adversarial.py)
```

#### Where `specialists.py` Fits in the Pipeline
[`app/agent/specialists.py`](../app/agent/specialists.py) is the **analytical engine room** of Stage 2. It contains the financial algorithms, forensic calculations, and prompt specifications for specialist diligence:

1. **`run_forensic_analysis(state, model)`** ([`specialists.py:203`](../app/agent/specialists.py:203)):
   - **Pipeline Position**: Stage 2 Diligence Sub-Agent (Engine 2: Forensic & Moat).
   - **Function**: Extracts 8 US-GAAP concepts, calculates the 8-Factor Beneish M-Score, Sloan Accrual Ratio, and SBC dilution burden, then uses the `FORENSIC_ACCOUNTING_PROMPT` to produce an audited earnings quality report.
2. **`run_moat_analysis(state, model)`** ([`specialists.py:322`](../app/agent/specialists.py:322)):
   - **Pipeline Position**: Stage 2 Diligence Sub-Agent (Engine 2: Forensic & Moat).
   - **Function**: Evaluates Hamilton Helmer's 7 Powers (switching costs, network effects, cost advantages, counter-positioning) using `MOAT_ANALYSIS_PROMPT`.
3. **`run_quant_analysis(state)`** ([`specialists.py:427`](../app/agent/specialists.py:427)):
   - **Pipeline Position**: Stage 2 Diligence Sub-Agent (Engine 3: Quant DCF) AND standalone tool `evaluate_valuation`.
   - **Function**: Executes deterministic DCF modeling via `app/valuation/engine.py::run_calculator` (`calculator.mjs`). It incorporates:
     - **Dynamic FRED WACC**: Derives risk-free rate $R_f$ from Federal Reserve `DGS10`, Blume-adjusted Beta, Damodaran ERP (4.75%), and capital-structure weights.
     - **CapEx Spike & Hyper-Growth Detection**: Normalizes maintenance CapEx ($15\%$ of revenue) during heavy investment cycles to avoid single-stage DCF distortion.
     - **Multi-Method Triangulation Payload**: Feeds forward EPS multiples ($10\times$), tangible book value floor ($1.8\times$), and consensus price targets to `calculator.mjs`.
4. **`run_sector_analysis(state, model)` & `run_thematic_analysis(state, model)`** ([`specialists.py:284, 359`](../app/agent/specialists.py:284)):
   - **Pipeline Position**: Supplementary Stage 2 specialist prompts for sector unit economics and macro thematic positioning.

#### The `conduct_candidate_diligence` Orchestrator
[`app/agent/diligence.py::run_candidate_diligence`](../app/agent/diligence.py:25) is the wrapper invoked by the tool `conduct_candidate_diligence(ticker)`. It:
1. Spawns an isolated synthetic state for the target candidate.
2. Automatically pulls missing market data or SEC financials.
3. Executes a **3-stage dependency-safe thread pipeline** (outer dossier contract unchanged):
   - **Stage 1 (parallel)**: `run_expectations_analyst()` from [`expectations.py:310`](../app/agent/expectations.py:310) (deterministic reverse DCF & expectation gap), `run_forensic_analysis()` from [`specialists.py:203`](../app/agent/specialists.py:203) (Beneish M-Score & forensics), `run_moat_analysis()` from [`specialists.py:322`](../app/agent/specialists.py:322) (economic moat rating), and `run_channel_check_analysis()` from [`specialists.py:488`](../app/agent/specialists.py:488) (Scuttlebutt receipts & Point72 concordance matrix) run concurrently with exception shielding.
   - **Stage 2 (synchronous)**: `run_quant_analysis()` from [`specialists.py:427`](../app/agent/specialists.py:427) (deterministic DCF & valuation) consumes Stage 1's `expectation_gap` assumptions.
   - **Stage 3 (parallel)**: `run_bull_advocate()` from [`bull.py`](../app/agent/bull.py) (catalysts & numeric target with one structured retry) and `run_adversarial_red_team()` from [`adversarial.py`](../app/agent/adversarial.py) (kill criteria & bear floor) run air-gapped and concurrently.
4. `build_diligence_dossier()` ([`diligence.py:154`](../app/agent/diligence.py:154)) packages the results into the standardized `diligence_dossier` dictionary and saves it onto the candidate workspace. The dossier additionally carries `bull_target_price`, per-report honest statuses (`bull_report_status` / `bear_report_status`), `channel_check_report`, and the full `moat_report` so the committee deliberates on every specialist's work.

---

### Stage 3: Evidence Ingestion (`ingest` node)

- **Graph Node Name**: `"ingest"`
- **Implementation**: `ingest_node(state)` in [`app/agent/graph.py:325`](../app/agent/graph.py)
- **Primary Source Files**:
  - [`app/agent/tool_result_ingestion.py`](../app/agent/tool_result_ingestion.py) (`ingest_tool_results`, `_distill_fact_cards`)
  - [`app/agent/ledger.py`](../app/agent/ledger.py) (`append_ledger_event`, `SourceDocument`)
  - [`app/agent/screening.py`](../app/agent/screening.py) (`FactCard`)

#### Execution Flow
1. **Tool Message Scanning**: Locates newly appended `ToolMessage` payloads from the trailing execution turn.
2. **Payload Parsing & Routing**: `ingest_tool_results()` routes payloads to their respective candidate workspaces:
   - SEC financials $\rightarrow$ stored under `candidate["sec_financials"]`.
   - Market data $\rightarrow$ stored under `candidate["market_context"]`.
   - Diligence dossiers $\rightarrow$ stored under `candidate["diligence_dossier"]`.
3. **Atomic FactCard Distillation**: `_distill_fact_cards()` converts tabular metrics (revenue, FCF, net debt, margins, DIO, DSO) into cited, timestamped `FactCard` instances (`fact_{ticker}_{metric}_{period}`). These cards are stored in `state["fact_cards"]` and `candidate["fact_cards"]`.
4. **Immutable Ledger Logging**: Writes immutable search and citation receipts to disk via `append_ledger_event()` in [`ledger.py:144`](../app/agent/ledger.py).
5. **Work Queue Progress**: Inspects completed tool receipts and candidate dossiers to advance corresponding `work_queue` items from `"queued"` to `"completed"`.
6. **State Transition**: Unconditionally routes back to `"executor"` for the next agent turn.

---

### Stage 4: Gap Reflection (`reflect` node)

- **Graph Node Name**: `"reflect"`
- **Implementation**: `reflection_node(state)` in [`app/agent/graph.py:360`](../app/agent/graph.py)
- **Router Function**: `should_continue_reflection(state)` in [`app/agent/graph.py:118`](../app/agent/graph.py)
- **Primary Source Files**:
  - [`app/agent/planning.py`](../app/agent/planning.py) (`reflect_on_research_gaps`, `ResearchReflectionSchema`)
  - [`app/agent/graph.py`](../app/agent/graph.py) (`_has_evidence_gaps`)

#### Execution Flow
1. **Structured Reflection**: Calls `reflect_on_research_gaps()` via LLM structured outputs to review collected evidence against the initial `ResearchPlanSchema`.
2. **Deterministic Integrity Checks**: Augments LLM reflection with programmatic assertions:
   - Does every active candidate have market context?
   - Does every active candidate have verified SEC financial coverage?
   - Has `conduct_candidate_diligence` or `evaluate_valuation` been executed for each un-vetoed candidate?
   - If multiple candidates exist, has `compare_candidates` been called?
   - Are there unread earnings/financial PDFs?
3. **Fast-Path Early Veto**: If a candidate workspace has `status="vetoed"` or a `veto_reason` (e.g. fraudulent accounting or uninvestable debt load), reflection permanently bypasses diligence requirements for that ticker.
4. **Routing Decision**:
   - If gaps are found and `reflection_count < max_reflection_rounds` (default 2), injects a targeted `HumanMessage` listing actionable gaps and routes back to `"executor"`.
   - If all gaps are resolved or reflection rounds are exhausted, routes forward to `"diligence"` (The Boardroom).

---

### Stage 5: Final Decision & Governance (`diligence` node)

- **Graph Node Name**: `"diligence"`
- **Implementation**: `diligence_node(state)` in [`app/agent/graph.py:430`](../app/agent/graph.py)
- **Primary Source Files**:
  - [`app/agent/gate.py`](../app/agent/gate.py) (G1 Evidence Gate, G2 Accounting Gate, G3 Valuation Gate, G4 Asymmetry Gate)
  - [`app/agent/committee.py`](../app/agent/committee.py) (`run_investment_committee`, `ICVerdict`)
  - [`app/agent/memo.py`](../app/agent/memo.py) (`render_research_report`, `render_forensic_memo`)

#### Execution Flow
1. **Evidence Gate (G1)**: `evaluate_research_completeness()` verifies that primary SEC filings, real-time market data, and required candidate workspaces exist. If G1 fails and the user requested an investment position, execution halts immediately without issuing an ungrounded recommendation.
2. **Unified 3-Mandate Routing**:
   - **Top-Down Macro / Thematic**: If the query is macroeconomic or thematic with zero equity candidates (`candidates={}`), `diligence_node` calls `run_macro_investment_committee()`, deterministically classifying monetary policy and yield curve regimes from FRED data, and generating a `MacroDirective` with sector tilts.
   - **Cross-Sectional Screening**: In multi-candidate screening mode, workspaces are preserved for cross-peer comparison, and Candidate #1 (the Top Pick by reward-to-risk ratio) is promoted to `top_candidate_ticker` for standalone CIO audit.
   - **Bottom-Up Single Stock**: The single candidate dossier (DCF fair value, Bull catalysts & numeric target, Bear kill criteria & floor, Beneish verdict, full moat report, and channel check report) is promoted into top-level state variables.
3. **Governance Gates (Instant Deterministic Math)**:
   - **Accounting Gate (G2)**: `evaluate_accounting_gate()` checks the Beneish M-Score ($M \le -1.78$).
   - **Valuation Gate (G3)**: `evaluate_valuation_gate()` verifies calculator reproducibility and reasonable growth hurdles.
   - **Asymmetry Gate (G4)**: `evaluate_asymmetry_gate()` enforces the reward-to-risk hurdle from the deterministic DCF risk/reward (the committee applies the configured `asymmetry_hurdle`, default $3.0\times$). Data integrity failures (`validation_required`) are strictly separated from disciplined strategic PASS / watchlist conclusions (`fails_asymmetric_hurdle` with actionable limit order guidance).
4. **Investment Committee Deliberation**: `run_investment_committee()` ([`committee.py:154`](../app/agent/committee.py:154)) runs a single formal CIO deliberation using `CIO_SYSTEM_PROMPT`. It:
   - Synthesizes Bull upside catalysts versus Bear kill criteria with **enforced anchor provenance**: the payload separates `upside_anchor` (source: `consensus_mean` / `quant_fair_value` / `bull_target_price` / `consensus_high_fallback`) from `dcf_base_fair_value`, records `bear_anchor_source` (`red_team_bear_floor` / `dcf_low_fallback`), and the CIO must cite the anchor source accurately in `anchor_citation`.
   - Enforces the strict "Passing Discipline" (rejecting cyclical peak multiples, commoditized capex traps, or excessive debt).
   - Applies **tiered sizing** from config-driven hurdles in `budget_state`: ratio $< 2.0\times$ → `VALIDATION_WATCH`; $[2.0\times, \text{hurdle})$ → `PAPER_TRADE_WATCH` (`paper_trade: true`, zero capital, kept for calibration); $\ge$ hurdle → quarter-Kelly (8% cap); $\ge 5.0\times$ with fully available debate reports → half-Kelly (10% cap).
   - Outputs an `ICVerdict` schema with verdict, conviction tier, tiered Kelly position size, anchor fields, `paper_trade`, and `bear_floor`.
5. **State Transition**: Connects directly to `END`.

---

## 3. Supporting Infrastructure Modules

The remaining modules in `app/agent/` provide the runtime, state, and serialization backbone for the pipeline:

| Module | Role & Key Responsibilities |
|---|---|
| [`app/agent/state.py`](../app/agent/state.py) | Defines `InvestigationState` (the TypedDict carried across all graph nodes), `ResearchRequest`, `ResearchIntent`, and `create_initial_state()`. |
| [`app/agent/context.py`](../app/agent/context.py) | Implements pair-safe LLM context window compaction (`prepare_context`, `ModelContextPolicy`). Prevents broken tool-call history while preserving entity backlinks. |
| [`app/agent/prompts.py`](../app/agent/prompts.py) | Builds the comprehensive research prompt (`build_research_system_prompt`), reprojection packets, and durable state blocks. |
| [`app/agent/ledger.py`](../app/agent/ledger.py) | Manages immutable evidence ledgers, citation records (`SourceDocument`, `SourceExcerpt`, `ClaimRecord`), and disk serialization. |
| [`app/agent/screening.py`](../app/agent/screening.py) | Implements multi-candidate workspace models (`CandidateResearchState`, `ScreenCandidate`, `ComparisonCard`) and cross-peer comparison logic (`build_candidate_comparisons`). |
| [`app/agent/adversarial.py`](../app/agent/adversarial.py) | Implements the hostile Bear Red Team analyst (`run_adversarial_red_team`, `AdversarialReport`) with field-level tolerance and honest `status`/`degradation_reasons`. |
| [`app/agent/bull.py`](../app/agent/bull.py) | Implements the air-gapped Bull Advocate (`run_bull_advocate`, `BullReport`) that models operating leverage, catalyst upside, and a numeric `bull_target_price` (one structured retry before flagging `degraded`). |
| [`app/agent/expectations.py`](../app/agent/expectations.py) | Implements the Expectations Analyst (`run_expectations_analyst`, `ExpectationGapAnalysis`). Implied growth, expectation edge, and the gap verdict are **deterministic** (calculator reverse DCF + consensus spread classification); model text is validated commentary, replaced and flagged `degraded` on contradiction. |
| [`app/agent/memo.py`](../app/agent/memo.py) | Formats final deliverables: `render_research_report()` (Markdown research memo), `render_forensic_memo()`, and `serialize_investigation_json()`. |
| [`app/agent/runner.py`](../app/agent/runner.py) | Entry point for CLI and services (`run_investigation()`). Compiles the graph, streams progress events, and writes results to disk. |
| [`app/agent/model_runtime.py`](../app/agent/model_runtime.py) | Configures LLM providers, model bindings, fallback chains, and temperature/token policies. |
| [`app/agent/sanitizer.py`](../app/agent/sanitizer.py) | Sanitizes user inputs, tickers, and file paths before state initialization. |
| [`app/agent/media.py`](../app/agent/media.py) | Downstream post-pipeline stage: converts finalized research memos and verdicts into grounded video scripts, TTS audio, and render assets. |
| [`tools/backtest_score.py`](../tools/backtest_score.py) | Decision-scoring harness: grades persisted cases against forward 3/6/12-month returns (injectable price provider) — hit rate, realized vs predicted upside, calibration error per verdict bucket. |

---

## 4. End-to-End File-to-Node Reference Matrix

| File Path | Primary Function / Class | Pipeline Stage / Node | Direct Caller / Trigger | Key Output / State Mutation |
|---|---|---|---|---|
| `app/agent/graph.py` | `planner_node` | Stage 1 (`planner`) | Graph entry point | `research_plan`, `work_queue`, `candidates` |
| `app/agent/planning.py` | `generate_research_plan` | Stage 1 (`planner`) | `planner_node` | `ResearchPlanSchema` |
| `app/agent/graph.py` | `executor_node` | Stage 2 (`executor`) | `planner` or `ingest` or `reflect` | `messages` (AIMessage with `tool_calls`) |
| `app/agent/tools.py` | `create_agent_tools` | Stage 2 (`tools`) | `executor_node` | Dispatches tools to external providers |
| `app/agent/diligence.py` | `run_candidate_diligence` | Stage 2 (`tools`) | Tool `conduct_candidate_diligence` | `diligence_dossier` on candidate workspace |
| `app/agent/expectations.py` | `run_expectations_analyst` | Stage 2 Sub-Agent | `run_candidate_diligence` | `expectation_gap` analysis |
| `app/agent/specialists.py` | `run_forensic_analysis` | Stage 2 Sub-Agent | `run_candidate_diligence` | `forensic_report` (Beneish M-Score, Sloan) |
| `app/agent/specialists.py` | `run_moat_analysis` | Stage 2 Sub-Agent | `run_candidate_diligence` | `moat_report` (7 Powers assessment) |
| `app/agent/specialists.py` | `run_channel_check_analysis` | Stage 2 Sub-Agent | `run_candidate_diligence` | `channel_check_report` (Concordance matrix) |
| `app/agent/specialists.py` | `run_quant_analysis` | Stage 2 Sub-Agent / Tool | `run_candidate_diligence`, `evaluate_valuation` | `quant_report` (DCF, WACC, Triangulation) |
| `app/valuation/calculator.mjs` | `compute` | Stage 2 Engine | `run_quant_analysis` via `engine.py` | Fair value range, Triangulation, Reverse DCF |
| `app/agent/bull.py` | `run_bull_advocate` | Stage 2 Sub-Agent | `run_candidate_diligence` | `bull_report` (Catalysts, upside target) |
| `app/agent/adversarial.py` | `run_adversarial_red_team` | Stage 2 Sub-Agent | `run_candidate_diligence` | `adversarial_report` (Kill criteria, floor) |
| `app/agent/screening.py` | `build_candidate_comparisons` | Stage 2 Tool | Tool `compare_candidates` | `comparisons` matrix across candidates |
| `app/sec/sec_agent.py` | `investigate_sec` | Stage 2 Sub-Agent | Tool `investigate_sec` | Verified filing excerpts and claims |
| `app/agent/graph.py` | `ingest_node` | Stage 3 (`ingest`) | `tools` node | Dispatches to `tool_result_ingestion.py` |
| `app/agent/tool_result_ingestion.py` | `ingest_tool_results` | Stage 3 (`ingest`) | `ingest_node` | `fact_cards`, `candidates`, `work_queue` |
| `app/agent/graph.py` | `reflection_node` | Stage 4 (`reflect`) | `executor_node` (no tool calls) | `HumanMessage` with gap prompts, budget update |
| `app/agent/planning.py` | `reflect_on_research_gaps` | Stage 4 (`reflect`) | `reflection_node` | `ResearchReflectionSchema` |
| `app/agent/graph.py` | `diligence_node` | Stage 5 (`diligence`) | `reflect` (complete) or `executor` | Final governance audit & verdict |
| `app/agent/gate.py` | `evaluate_research_completeness` | Stage 5 (`diligence`) | `diligence_node` | `evidence_gate` (G1) |
| `app/agent/gate.py` | `evaluate_accounting_gate` | Stage 5 (`diligence`) | `diligence_node` | `accounting_gate` (G2) |
| `app/agent/gate.py` | `evaluate_valuation_gate` | Stage 5 (`diligence`) | `diligence_node` | `valuation_gate` (G3) |
| `app/agent/gate.py` | `evaluate_asymmetry_gate` | Stage 5 (`diligence`) | `diligence_node` | `asymmetry_gate` (G4) |
| `app/agent/committee.py` | `run_investment_committee` | Stage 5 (`diligence`) | `diligence_node` | `ic_verdict`, `investment_committee` |
| `app/agent/committee.py` | `run_macro_investment_committee` | Stage 5 (`diligence`) | `diligence_node` (macro) | `macro_directive` (monetary & yield curve tilts) |
| `app/agent/memo.py` | `render_research_report` | Output Generation | Runner after graph finishes | Comprehensive Markdown research memo |
| `app/agent/runner.py` | `run_investigation` | Top-level Orchestrator | CLI / Web Studio / Automation | Executes graph from `START` to `END` |
