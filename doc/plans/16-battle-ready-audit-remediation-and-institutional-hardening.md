# Execution Plan 16 — Financial Accuracy, SEC Extraction Fixes & Reel Integrity

## Purpose

Fix concrete data, parsing, and financial reporting defects identified in the system audit to ensure the agent produces **accurate financial research memos** and **grounded viral video reel scripts**. 

This plan ruthlessly applies YAGNI (Ponytail principle): we eliminate speculative enterprise infrastructure (no SSRF proxy layers, no distributed locks, no containerization, no LLM backtesting) and focus 100% on **data correctness, genuine accounting facts, and fail-closed reporting**.

---

## What We Cut (YAGNI / Enterprise Bloat)

- ❌ **SSRF & internal proxy networks**: Unnecessary for a local research agent.
- ❌ **Circuit breakers, distributed locks, Kubernetes/Docker images**: Unnecessary for single-user local CLI runs.
- ❌ **Complex LLM backtesting suite**: Model weights already memorized historical market data; lookahead contamination makes automated backtesting unreliable. Deferred to a post-v1 backlog.
- ❌ **Enterprise audit event buses**: Local JSON and Markdown case files already provide full traceability.

---

## Core Fixes Matrix (What Actually Matters)

| ID | Module | Issue / Bug | Fix |
|---|---|---|---|
| **FIX-01** | `app/agent/tools.py` | `pull_sec_filings` creates `SelectedSecDocument` with direct fields instead of nested `FilingMetadata`, breaking real SEC pulls. | Instantiate complete `FilingMetadata` and pass `SelectedSecDocument(filing=...)`. |
| **FIX-02** | `app/sec/financials.py` | XBRL parsing mixes YTD cumulative flow facts with discrete quarters and assumes provider columns are newest-first. | Distinguish discrete 3-month durations from YTD, sort by fiscal end-date, and derive discrete Q2/Q3 values from cumulative YTD figures. |
| **FIX-03** | `app/agent/committee.py` | Committee invents fake defaults ($100 price, 30% upside, 15% downside, and implicit high confidence) when data is missing. | Fail closed: missing/zero data returns `UNAVAILABLE` / `VALIDATION_WATCH` with strictly `0.0%` position size. |
| **FIX-04** | `app/agent/committee.py` | 2.0x–2.99x asymmetry receives `APPROVED_LONG_MEDIUM` with nonzero Kelly allocation, violating the 3.0x rule. | Enforce strict 3.0x hurdle: ratio < 3.0x strictly assigns `0.0%` position size. |
| **FIX-05** | `app/agent/media.py` | When reel dialogue generation fails, fallback emits canned claims ("10-Q confirmed gross margin expansion"). | Fail cleanly without hallucinating financial facts; output neutral error script or abort gracefully. |
| **FIX-06** | `app/agent/tools.py` | Tool checks for `faiss.index` while retrieval writes `sec.faiss`, triggering redundant index builds. | Standardize on shared `sec.faiss` constant. |
| **FIX-07** | `app/sec/default_assessor.py` | Offline fallback confirms claims based on 2-word lexical overlap. | Offline fallback must strictly return `INSUFFICIENT_EVIDENCE`. |

---

## Implementation Details

### 1. Fix SEC Filing Pull Tool (`app/agent/tools.py`)
In `pull_sec_filings` tool wrapper, properly construct `FilingMetadata`:
```python
selected_docs = [
    SelectedSecDocument(
        filing=FilingMetadata(
            accession=s["accession"],
            form=s["form"],
            filing_date=s["filing_date"],
            report_date=s.get("report_date", s["filing_date"]),
            cik=s.get("cik", "0000000000"),
            ticker=s.get("ticker", "UNKNOWN"),
        ),
        document_name=s["document_name"],
        source_url=s["source_url"],
    )
    for s in selections
]
```

### 2. Fix SEC XBRL Duration & Sorting (`app/sec/financials.py`)
- **Duration vs Instant**: Ensure balance sheet items (cash, debt, inventory) use instant contexts, and income/cash-flow items (revenue, gross profit, CapEx) use duration contexts.
- **Discrete Quarter Math**: If a 10-Q statement gives 6-month YTD revenue, subtract Q1 revenue to get discrete Q2 revenue.
- **Chronological Sorting**: Sort periods by `period_end_date` before computing QoQ inventory and margin changes.

### 3. Fail-Closed Financial Reporting (`app/agent/committee.py`)
- If `current_price` is missing or `<= 0`: return `VALIDATION_WATCH` with `kelly_position_size_pct = 0.0`.
- If `base_target` is missing or `<= current_price`: return `VALIDATION_WATCH` with `kelly_position_size_pct = 0.0`.
- If `bear_floor` is missing, `<= 0`, or `>= current_price`: return `VALIDATION_WATCH` with `kelly_position_size_pct = 0.0`.
- If `ratio < 3.0`: return `VALIDATION_WATCH` or `PASSED_STRICT_DISCIPLINE` with `kelly_position_size_pct = 0.0`.
- If `confidence` is `None` or `< 0.70`: do not allow `APPROVED_LONG_HIGH`.

### 4. Grounded Media Generation Fallback (`app/agent/media.py`)
- Remove canned statements asserting margin growth or demand surges.
- If model generation fails, return a safe neutral dialogue:
  `"(skeptical) We couldn't verify this ticker's numbers yet. (confident) Check the raw audit memo below for details."`

### 5. Index Filename Alignment (`app/agent/tools.py`)
- Align `verify_sec_claim` index existence check to `sec.faiss` matching `app/sec/retrieval.py`.

### 6. Fail-Closed Offline SEC Assessor (`app/sec/default_assessor.py`)
- In offline mode without API keys, return `verdict="INSUFFICIENT_EVIDENCE"` and `confidence=0.0`.

---

## Acceptance Criteria

1. **Tool Invocation**: `pull_sec_filings` executes cleanly when given output from `list_sec_filings`.
2. **Accounting Correctness**: SEC financials extraction correctly handles discrete quarters and chronological order.
3. **No Fake Numbers**: Missing price/target/floor/confidence produces `0.0%` position size in `ic_verdict`.
4. **Strict 3:1 Hurdle**: Ratios of 2.5x or 2.99x receive `0.0%` position size and `VALIDATION_WATCH`.
5. **Clean Video Scripts**: Media generation never outputs fake "10-Q confirmed margin expansion" claims when model parsing fails.
6. **Full Suite**: All unit and integration tests pass cleanly with `pytest`.
