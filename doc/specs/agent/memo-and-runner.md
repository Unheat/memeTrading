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
1. Atomically claims a distinct `cases/<case_id>/` directory via `app.storage.cases` and immediately writes a `run-manifest.json` in `running` state.
2. Initializes `InvestigationState` with request metadata and initial human prompt.
3. Compiles and executes the LangGraph agent graph. A deterministic research-completeness gate runs after the tool loop and before red-team/committee stages.
4. If required identity, market, and SEC evidence is absent, terminal state is `insufficient_evidence` with deterministic `NO_POSITION`; it bypasses red-team/committee and optional media.
5. Renders `memo.md` and `investigation.json`, preserving gate state, tool/source receipts, corpus references, consensus, expectation gap, adversarial report, and committee verdict. Core artifacts are atomically written.
6. Marks `run-manifest.json` `completed` on every rendered research outcome, or `failed` with sanitized diagnostic data when graph/core rendering fails. Existing cases are never deleted or overwritten.
7. Returns `InvestigationResult(case_id, ticker, status, memo_markdown, final_state)`.

42	### Incomplete and validation rendering
43	`render_forensic_memo` always renders sections 1–8. For `insufficient_evidence` or G2/G3/G4 validation outcomes it sets `NO_POSITION` and 0.0% allocation, lists unavailable prerequisites, and does not embed raw model final text, price targets, entries, bear floors, rankings, generic numeric kill triggers, or any generated/uncited financial number. Unknown fields render `Unavailable — not inferred`.

## Donor code provenance

| Local symbol | Reuse type | Exact donor location | Deliberate changes |
| --- | --- | --- | --- |
| `app.agent.gate.evaluate_research_completeness` | adapted | `reference/ai-hedge-fund/hedge_fund/signals/llm_agent.py:54-95,164-172`, outcome handling | Local deterministic evidence checks; no signal/backtest architecture or LLM decision parsing. |
| `app.agent.runner.run_investigation` manifest transitions | adapted | `reference/ai-financial-research-agent/app/api/schemas.py:13-19,64-84`, `reference/ai-financial-research-agent/app/api/service.py:81-94,163-198` | Local filesystem manifest only; no FastAPI, SQLite, threads, or event fanout. |
| `app.agent.memo.render_forensic_memo` missing-value display | adapted | `reference/financial-research-workshop/skills/earnings-summary/SKILL.md:8-28`, `reference/financial-research-workshop/skills/investor-note/SKILL.md:8-21` | Uses deterministic `Unavailable — not inferred`; raw model prose is blocked for insufficient evidence. |
