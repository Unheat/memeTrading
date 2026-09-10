# Module Spec — `app/agent/memo.py` and `app/agent/runner.py`

## Responsibility

Deterministic generation of the evidence-backed forensic markdown memo (`memo.md`), structured JSON audit artifact (`investigation.json`), and the high-level `run_investigation` runner.

## `app/agent/memo.py`

### `render_forensic_memo(state: InvestigationState, final_text: str) -> str`
Generates a Github-flavored Markdown memo containing:
1. **Header**: Ticker, Company, CIK, Investigation Timestamp, Final Verdict / Confidence.
2. **1. Narrative Origin & Social Trigger**: Social mention spikes, velocity, unique author ratio, hype narrative.
3. **2. Core Claims & Reality Check**:
   - Table of Hype Claims vs SEC/Primary Truth.
4. **3. SEC Filing Evidence & Audit Trail**:
   - Table citing: Form, Accession, Filing Date, Direct URL, Verbatim Quotation.
5. **4. Dilution, Financing & Structural Risks**:
   - Authorized vs outstanding shares, ATM capacity, S-1/S-3 shelves, warrant overhang, convertible notes.
6. **5. Insider Activity & Management Conduct**:
   - Form 4 transactions, code analysis (sales vs option exercises), footnotes.
7. **6. Market Pricing Context**:
   - Returns (1d, 5d, 1m, 3m), volume ratio vs 20d baseline, benchmark-relative return, expectation gap.
8. **7. Unresolved Questions & Thesis Breakers**:
   - Remaining uncertainties, paywalled/unreachable sources, conditions that would invalidate the thesis.
9. **8. Forensic Conclusion**:
   - Synthesis paragraph summarizing evidence strength and commercial viability.

### `serialize_investigation_json(state: InvestigationState, memo_md: str) -> dict`
Generates the complete JSON audit trail suitable for programmatic analysis or static-site publication.

## `app/agent/runner.py`

### `run_investigation(request: ResearchRequest, model=None, cases_root=None) -> InvestigationResult`
1. Creates case ID and folder in `cases/<case_id>/` via `app.storage.cases`.
2. Initializes `InvestigationState` with request metadata and initial human prompt.
3. Compiles and executes the LangGraph agent graph.
4. Renders `memo.md` and `investigation.json` and writes them atomically to the case folder.
5. Returns `InvestigationResult(case_id, ticker, status, memo_markdown, final_state)`.
