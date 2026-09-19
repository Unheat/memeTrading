# 💻 MemeForensics CLI Guide & Command Reference

Complete command-line documentation for the **MemeForensics** deep research agent, historical backtesting harness, deterministic valuation calculator, and media synthesis pipelines.

---

## 📑 Table of Contents

- [1. Research Agent CLI (`main.py`)](#1-research-agent-cli-mainpy)
  - [Core Operational Modes](#core-operational-modes)
  - [Complete Arguments Reference](#complete-arguments-reference)
  - [Media Generation Suite (Opt-in)](#media-generation-suite-opt-in)
  - [Point-in-Time (PIT) Discipline](#point-in-time-pit-discipline)
  - [Production Recipes](#production-recipes)
- [2. Historical Backtest Sweep CLI (`scripts/run_backtest.py`)](#2-historical-backtest-sweep-cli-scriptsrun_backtestpy)
  - [Evaluation Mechanics](#evaluation-mechanics)
  - [CLI Arguments Reference](#cli-arguments-reference)
  - [Execution Examples](#execution-examples)
  - [Scorecard Metrics & Interpretation](#scorecard-metrics--interpretation)
- [3. Standalone Valuation Calculator CLI (`app/valuation/calculator.mjs`)](#3-standalone-valuation-calculator-cli-appvaluationcalculatormjs)
  - [Execution Modes](#execution-modes)
  - [JSON Model Schema](#json-model-schema)
- [4. Pipeline E2E Audit (`run_e2e_audit.py`)](#4-pipeline-e2e-audit-run_e2e_auditpy)
- [5. Faceless Media Diagnostics (`faceless/`)](#5-faceless-media-diagnostics-faceless)

---

## 1. Research Agent CLI (`main.py`)

`main.py` is the primary interface for autonomous equity diligence, multi-candidate discovery, and SEC forensic auditing.

```bash
python main.py [OPTIONS]
```

### Core Operational Modes

#### Interactive Prompt Mode
Running without arguments prompts interactively for your research idea or query:
```bash
python main.py
```

#### Single Ticker Forensic Diligence
Investigate an individual company against an earnings narrative or risk hypothesis:
```bash
python main.py --ticker MU --query "Investigate DDR5 memory shortages and gross margin expansion"
```

#### Thematic & Grassroots Beneficiary Discovery
Explore an entire market narrative without naming a stock upfront. The agent searches grassroots signals, identifies supply chain choke-points, and registers public candidates automatically:
```bash
python main.py --query "Is there a cloud GPU wait time bottleneck for NVDA and hyperscalers? Trace key beneficiaries and verify against 10-Q Capex"
```

---

### Complete Arguments Reference

| Argument | Short | Type | Default | Description |
| :--- | :---: | :---: | :---: | :--- |
| `--query` | `-q` | `str` | `None` | Research prompt, thesis, or question to investigate. Prompted interactively if omitted. |
| `--ticker` | `-t` | `str` | `None` | Target equity ticker symbol (e.g. `MU`, `NVDA`, `TSLA`, `AAPL`). |
| `--company` | `-c` | `str` | `None` | Full legal corporate entity name (e.g. `"Micron Technology"`). |
| `--theme` | | `str` | `None` | Industry narrative or macro theme (e.g. `"DDR5 Shortage"`, `"GLP-1 Weight Loss"`, `"AI Power"`). |
| `--mandate` | | `str` | `None` | Specific research angle or risk policy (e.g. `"Capital Preservation"`, `"Forensic Accounting Focus"`). |
| `--depth` | | `choice` | `deep` | Research breadth and tool budget policy. Choices: `standard` (15–25 tool calls), `deep` (35–50 tool calls). |
| `--as-of` | | `str` | `None` | Historical Point-in-Time analysis cutoff date in `YYYY-MM-DD` format. Excludes lookahead filings and drops undated web items. |
| `--article` | | `flag` | `False` | Generate a cited Substack-style forensic article (`article.md`). |
| `--video` | | `flag` | `False` | Generate article, dialogue script, and render 1080x1920 video reel (`.mp4`) via local Faceless pipeline. |
| `--video-script-only` | | `flag` | `False` | Generate article and dialogue script (`faceless/dialogue.json`), but skip video rendering. |
| `--article-video`<br/>`--media` | | `flag` | `False` | Generate both the cited article and the rendered viral video reel. |
| `--character-pair` | | `choice` | `config` | Character duo for viral dialogue. Choices: `peter_stewie` (Peter & Stewie Griffin), `rick_morty` (Rick Sanchez & Morty Smith). |
| `--verbose` | `-v` | `flag` | `False` | Enable detailed terminal debug logs showing tool calls, state transitions, and raw JSON payloads. |

---

### Media Generation Suite (Opt-in)

By default, `main.py` runs lean and fast, emitting only the institutional investment memo (`memo.md`) and structured state (`investigation.json`). You can opt into media generation via flags:

```bash
# 1. Generate Substack-style deep dive article only
python main.py -t NVDA -q "Analyze Blackwell rack thermal limits" --article

# 2. Generate article + dialogue script without video rendering
python main.py -t NVDA -q "Analyze Blackwell rack thermal limits" --video-script-only

# 3. Generate article + dialogue script + rendered .mp4 video reel
python main.py -t NVDA -q "Analyze Blackwell rack thermal limits" --video

# 4. Generate full media suite with Rick & Morty character pair
python main.py -t MU -q "DRAM cycle pricing power" --article-video --character-pair rick_morty
```

---

### Point-in-Time (PIT) Discipline

When `--as-of YYYY-MM-DD` is specified:
1. **SEC Filings Clamping:** Filings (`10-K`, `10-Q`, `8-K`) with filing dates after the cutoff date are strictly filtered out of catalog searches and download requests.
2. **Web & Article Filtering:** Articles or web search results with publication dates past the cutoff are removed.
3. **Undated Content Dropped:** In historical backtest mode, undated web content is dropped to prevent lookahead contamination. In live mode (`--as-of` omitted), undated content is preserved.

---

### Production Recipes

#### Recipe 1: Semiconductor Cycle & Inventory Drift
```bash
python main.py \
  --ticker MU \
  --query "DRAM cycle pricing power, inventory DIO drift, and HBM3E gross margin trajectory" \
  --depth standard
```

#### Recipe 2: Thematic Multi-Candidate Discovery
```bash
python main.py \
  --query "Which semiconductor equipment makers benefit most from high-NA EUV lithography adoption?" \
  --theme "Advanced Lithography" \
  --depth deep
```

#### Recipe 3: Historical Post-Mortem Audit
```bash
python main.py \
  --ticker SMCI \
  --as-of 2024-03-01 \
  --query "Forensic audit of revenue recognition, inventory turnover, and related-party disclosures" \
  --verbose
```

#### Recipe 4: Viral Video Reel Production
```bash
python main.py \
  --ticker TSLA \
  --query "Robotaxi regulatory approval path, FSD take rates, and auto gross margin floor" \
  --article-video \
  --character-pair peter_stewie
```

---

## 2. Historical Backtest Sweep CLI (`scripts/run_backtest.py`)

The backtest harness systematically evaluates investment committee verdicts and valuation accuracy across historical dates and tickers.

```bash
python scripts/run_backtest.py [OPTIONS]
```

### Evaluation Mechanics

1. **Date Grid Generation:** Computes evenly spaced calendar dates (`--step-days`) between `--start-date` and `--end-date`.
2. **Point-in-Time Diligence:** Runs the complete research agent for each ticker as of that date, clamping all data sources.
3. **Forward Alpha Settlement:** Evaluates investment committee verdicts after `--forward-days` (default 90 days), calculating realized returns against the `SPY` benchmark to compute excess return (alpha).
4. **Scorecard Compilation:** Aggregates verdict counts, hit rates, alpha differentials, and forensic warning indicators into an institutional scorecard.

---

### CLI Arguments Reference

| Argument | Short | Type | Default | Description |
| :--- | :---: | :---: | :---: | :--- |
| `--tickers` | `-t` | `str [str ...]` | **Required** | One or more stock tickers to evaluate (e.g. `NVDA AAPL MSFT`). |
| `--start-date` | | `str` | **Required** | Starting historical analysis date (`YYYY-MM-DD`). |
| `--end-date` | | `str` | **Required** | Ending historical analysis date (`YYYY-MM-DD`). |
| `--step-days` | | `int` | `30` | Cadence in calendar days between evaluation points. |
| `--forward-days` | | `int` | `90` | Forward settlement evaluation horizon in calendar days (e.g. 30, 60, 90). |
| `--output-dir` | | `str` | `cases/backtests` | Root directory where historical case folders will be saved. |
| `--verbose` | `-v` | `flag` | `False` | Enable detailed debug logging. |

---

### Execution Examples

#### 1-Year Historical Sweep for a Single Ticker
```bash
python scripts/run_backtest.py \
  --tickers MU \
  --start-date 2023-01-01 \
  --end-date 2024-01-01 \
  --step-days 60 \
  --forward-days 90
```

#### Multi-Ticker Peer Comparison Across Tech Leaders
```bash
python scripts/run_backtest.py \
  --tickers NVDA AAPL MSFT \
  --start-date 2023-01-01 \
  --end-date 2023-06-01 \
  --step-days 30 \
  --forward-days 90 \
  --output-dir cases/backtests
```

---

### Scorecard Metrics & Interpretation

The backtest runner emits an institutional scorecard formatted as follows:

```
========================================================================
 📊 INSTITUTIONAL DEEP RESEARCH BACKTEST SCORECARD
========================================================================
• Forward Horizon:     90 days vs SPY
• Total Evaluations:   12 (Settled: 12, Pending: 0)

## 1. Investment Committee Verdict Distribution
  - Approved Longs:     3
  - Passed Discipline:  8
  - Validation Watch:   1

## 2. Decision Performance & Alpha vs Benchmark
  - Approved Longs Hit Rate:    100.0% (beat SPY)
  - Approved Longs Mean Alpha:  +18.42%
  - Passed Decisions Mean Alpha:-4.15%

## 3. Forensic & Capital Safety Safeguards
  - High Manipulation Risks:    2 flagged by Beneish/Sloan
  - High-Risk Realized Return:  -22.30%
  - Bear Floor Downside Breaches: 0
========================================================================
```

- **Approved Longs Hit Rate:** Percentage of committee-approved longs that outperformed the `SPY` benchmark over the forward window.
- **Approved Longs Mean Alpha:** Average annualized or holding-period excess return over `SPY` for approved positions.
- **Passed Decisions Mean Alpha:** Excess return of companies the committee rejected. A negative alpha confirms that passing protected capital from underperforming assets.
- **High Manipulation Risks:** Companies flagged by Beneish M-Score ($M > -1.78$) or extreme Sloan accruals.
- **Bear Floor Downside Breaches:** Count of instances where the stock traded below the hostile bear red team's catastrophic floor price.

---

## 3. Standalone Valuation Calculator CLI (`app/valuation/calculator.mjs`)

MemeForensics isolates deterministic financial calculations from model inference. The standalone Node.js calculator handles all reverse DCF math, scenario projections, and gate verifications.

```bash
node app/valuation/calculator.mjs <model.json> [OPTIONS]
```

### Execution Modes

#### Mode 1: Compute & Output JSON
Evaluates DCF cases, Reverse DCF implied growth, Graham number, and Asymmetry ratios, printing the result to stdout:
```bash
node app/valuation/calculator.mjs model.json
```

#### Mode 2: Compute & Write Back
Updates the input file in place with calculated fair values, sensitivity matrices, and risk/reward ratios:
```bash
node app/valuation/calculator.mjs model.json --write
```

#### Mode 3: Gate G3 Verification
Validates that model inputs, cash flows, discount rates, and growth assumptions satisfy mathematical reproducibility constraints:
```bash
node app/valuation/calculator.mjs model.json --verify
```

---

### JSON Model Schema

A minimal `model.json` input file contains:

```json
{
  "ticker": "MU",
  "share_price": 927.60,
  "shares_outstanding": 1115000000,
  "net_cash": 1250000000,
  "fcf_base": 3850000000,
  "wacc": 0.095,
  "terminal_growth_rate": 0.025,
  "dcf": {
    "forecast_years": 10,
    "cases": [
      { "case": "bear", "growth_rate": 0.04, "margin_expansion": -0.05 },
      { "case": "base", "growth_rate": 0.12, "margin_expansion": 0.02 },
      { "case": "bull", "growth_rate": 0.20, "margin_expansion": 0.06 }
    ]
  }
}
```

---

## 4. Pipeline E2E Audit (`run_e2e_audit.py`)

Run an end-to-end programmatic sanity audit against the full research pipeline:

```bash
python run_e2e_audit.py
```

Tests multi-candidate discovery, candidate workspace registration, tool call execution, and memo synthesis in a single automated pass.

---

## 5. Faceless Media Diagnostics (`faceless/`)

MemeForensics uses the local `faceless/` sub-system for synthesizing character voices and compiling MP4 reels.

```bash
# Run environment diagnostics (FFmpeg, Fish Audio API key, font checks)
node faceless/skills/faceless/scripts/doctor.mjs
```
