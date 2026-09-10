# Module Spec — `app/agent/state.py` and `app/agent/prompts.py`

## Responsibility

Define the typed request, budget, and investigation state for LangGraph, along with the dynamic forensic prompt generator.

## `app/agent/state.py`

### `BudgetLimits`
- `max_tool_calls: int = 15`
- `max_identical_calls: int = 2`

### `ResearchRequest`
- `query: str`: User's research request.
- `ticker: str | None`: Optional uppercase ticker.
- `company: str | None`: Optional company name.
- `theme: str | None`: Optional theme/narrative.
- `mandate: str | None`: Optional mandate (e.g. "catalyst_nowcast").
- `time_boundary: str | None`: Optional time window.
- `budget: BudgetLimits`: Budget configuration.
- `template_version: str | None`: Version of prompt template if automated.

### `InvestigationState(TypedDict)`
- `messages: Annotated[list[BaseMessage], add_messages]`
- `case_id: str`
- `ticker: str`
- `company: str | None`
- `cik: str | None`
- `trigger: dict[str, Any]`
- `root_claims: list[str]`
- `evidence: list[dict[str, Any]]`
- `contradictions: list[dict[str, Any]]`
- `unresolved_questions: list[str]`
- `sec_corpora: list[str]`
- `searches_performed: list[dict[str, Any]]`
- `confidence: float | None`
- `tool_calls: int`
- `status: str`
- `causal_chain: dict[str, str] | None`
- `market_context: dict[str, Any] | None`
- `thesis_breakers: list[str]`
- `budget_state: dict[str, Any]`

## `app/agent/prompts.py`

### `FORENSIC_CHARTER_PROMPT`
Defines the agent's identity:
- Forensic equities research investigator testing speculative hype against authoritative primary sources.
- Hierarchy of evidence: SEC filings > regulatory sources > company primary announcements > reputable financial press > social chatter.
- Skepticism and contradiction-seeking: check for non-binding terms, dilution capacity (S-1/S-3/ATM), warrants, insider sales (Form 4).
- Analytical lenses: Druckenmiller pricing check (is this priced in?), Lynch categorization, causal chain `signal -> demand/bottleneck -> beneficiary -> financial mechanism -> expectation gap`.

### `build_dynamic_system_prompt(state: InvestigationState) -> SystemMessage`
Injects the current structured facts into the prompt:
- Ticker, CIK, Company
- Verified Evidence so far
- Contradictions observed
- Remaining Unresolved Questions
- Remaining tool call budget
This ensures that even if old tool output messages are trimmed from `messages`, the model never loses the factual context.
