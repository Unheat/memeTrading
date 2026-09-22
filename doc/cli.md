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
- [6. Web Publishing & Cloudflare Edge Deployment (`app/cli/publish.py`)](#6-web-publishing--cloudflare-edge-deployment-appclipublishpy)
- [7. Local Studio GUI (`app/studio/`)](#7-local-studio-gui-appstudio)

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
| `--video` | | `flag` | `False` | Generate cited article (`article.md`), dialogue script derived from the article, and render 1080x1920 video reel (`.mp4`) via local Faceless pipeline. |
| `--video-script-only` | | `flag` | `False` | Generate cited article and dialogue script (`faceless/dialogue.json`) based on the article, but skip MP4 video rendering. |
| `--article-video`<br/>`--media` | | `flag` | `False` | Generate both the cited forensic article and the rendered viral video reel. |
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

# 3. Generate cited article + character dialogue derived from it + rendered .mp4 video reel
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

---

## 6. Web Publishing & Cloudflare Edge Deployment (`app/cli/publish.py`)

Synchronize local research case artifacts into the Astro Cloudflare website (`web/src/content/articles/`) with automated video optimization, interactive Wikipedia-style citation cards, client-side Pagefind indexing, and Cloudflare Workers/Pages edge deployment:

```bash
# 1. Publish the latest investigation to the Astro website (local sync only)
python -m app.cli.publish --latest

# 2. Publish and immediately build + deploy to Cloudflare Edge CDN (<20ms TTFB)
python -m app.cli.publish --latest --deploy

# 3. Publish a specific case folder
python -m app.cli.publish MU-2026-09-20-001 --deploy

# 4. List all currently published articles and their companion video status
python -m app.cli.publish --list

# 5. Delete an article and its companion video from the website and redeploy to Cloudflare
python -m app.cli.publish --delete mu-mu-2026-09-20-001 --deploy

# 6. Publish with an explicit external YouTube Video ID
python -m app.cli.publish MU-2026-09-15-007 --youtube-id dQw4w9WgXcQ --deploy

# 7. Or trigger directly through the main entrypoint
python main.py --publish-case MU-2026-09-20-001 --deploy
```

### Complete Publishing Arguments Reference

| Argument | Short / Flag | Default | Description |
| :--- | :---: | :---: | :--- |
| `case_id` | Positional | `None` | Case directory name (e.g. `MU-2026-09-20-001`) or relative path. Defaults to latest if omitted with `--latest`. |
| `--latest` | | `False` | Resolves the most recently created case directory in `cases/`. |
| `--list` | | `False` | Prints a summary table of all published articles on the website (slug, title, case ID, video asset URL). |
| `--delete` | `SLUG_OR_ID` | `None` | Deletes the matching Markdown article and companion video file from `web/`. Add `--deploy` to push deletions live to Cloudflare. |
| `--deploy` | | `False` | Executes `npm run build` (Astro static build + Pagefind Wasm index) and `npx wrangler deploy` to push changes to Cloudflare edge. |
| `--youtube` | | `True` | Automatically uploads the companion reel to YouTube if `client_secrets.json` is configured. |
| `--no-youtube` | | `False` | Skips YouTube API upload and hosts video directly on Cloudflare edge CDN. |
| `--privacy` | `CHOICE` | `unlisted` | Privacy level for YouTube uploads (`unlisted`, `public`, `private`). |
| `--youtube-id` | `ID` | `None` | Manually attaches an existing YouTube video ID instead of local edge hosting. |
| `--web-root` | | `web` | Path to the Astro website project root. |

---

### Video Delivery & Cloudflare Free Tier Architecture

MemeForensics supports dual video delivery modes:

#### 1. Native Cloudflare Edge Hosting (Default, Zero Config)
When YouTube credentials are not provided, the publishing engine automatically prepares the video for Cloudflare Edge hosting:
- **Cloudflare Free Tier Limits**:
  - **Individual Asset Cap**: Cloudflare Workers/Pages static assets enforce a strict **25 MiB** limit per file.
  - **Bandwidth / Data Transfer**: **100% Free and Unlimited** ($0 egress fees globally).
  - **Asset Quantity**: Up to **20,000 files** per project deployment.
- **Automated Web Optimization**:
  - Raw master reels rendered by Faceless are often 70–95 MB (at 7.5 Mbps bitrate).
  - If a video exceeds 24 MB, `publish.py` runs an automated optimization pass using `ffmpeg-static` to scale to 720×1280 at 1.4 Mbps with `+faststart` metadata (moving the `moov` atom to the front for zero-buffering mobile streaming).
  - This compresses the video to **~15–18 MB** (safely under the 25 MiB cap) and copies it to `web/public/videos/<slug>.mp4`.
  - The website serves it via a custom HTML5 `<video controls playsinline>` player without third-party ads or tracking.

#### 2. Automated YouTube Video Embeds (Optional)
If you configure Google Cloud OAuth2 credentials:
1. Place your downloaded `client_secrets.json` into the project root.
2. Run `python -m app.cli.publish --latest --youtube --privacy unlisted --deploy`.
3. The video is uploaded to your YouTube channel via the YouTube Data API v3 and embedded as a responsive vertical 9:16 player (`https://www.youtube.com/embed/<VIDEO_ID>`). Tokens are cached locally in `.youtube_token.json` for unattended future uploads.

---

### Managing Published Content (List & Delete)

To inspect your published portfolio:
```bash
python -m app.cli.publish --list
```
**Example Output:**
```text
📰 Published Articles on Website:
================================================================================
• Slug:    mu-mu-2026-09-20-001
  Title:   The Trillion-Dollar Silicon Mirage: Unpacking Micron’s 84% Gross Margin Peak
  Case:    MU-2026-09-20-001
  Video:   /videos/mu-mu-2026-09-20-001.mp4
--------------------------------------------------------------------------------
```

To purge an outdated case from the website:
```bash
# Delete markdown + video asset locally and redeploy immediately:
python -m app.cli.publish --delete mu-mu-2026-09-20-001 --deploy
```

---

### Staged Independent Video Generation (`app/media/cli.py`)
If you prefer a step-by-step editorial review workflow (run research & write the article first, inspect prose, and only then render video):
```bash
# Step 1: Run research + cited Substack article
python main.py --ticker MU --query "DRAM cycle pricing power" --article

# Step 2: Render video reel for that reviewed case (Peter & Stewie or Rick & Morty)
python -m app.media.cli video --case-id MU-2026-09-20-001 --character-pair peter_stewie

# Step 3: Publish to Cloudflare website
python -m app.cli.publish MU-2026-09-20-001 --deploy
```

---

## 7. Local Studio GUI (`app/studio/`)

A browser-based operator dashboard for running investigations, reviewing formatted articles with interactive citations, watching rendered vertical reels in-browser, and 1-click publishing to Cloudflare:

```bash
# Launch the Local Studio on http://127.0.0.1:3000
python -m app.studio

# Or via main.py
python main.py --studio
```

