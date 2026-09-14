# Module Spec — `app/agent/state.py` and `app/agent/prompts.py`

## Responsibility

Define the typed request, budget, investigation, and model-context policy state for LangGraph, along with the dynamic forensic prompt generator. Context management targets models with context windows up to 1M tokens without assuming every configured model or provider exposes that capacity.

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

### `ModelContextPolicy`
- Adaptive policy for the investigator model's ephemeral message context; it does not change permanent structured forensic state.
- Supports model context windows up to 1M tokens, while using a conservative default pruning threshold of 200,000 tokens when model/provider metadata does not establish a safer higher limit.
- Counts tokens with a model-aware counter when the configured model exposes one. A documented conservative estimator is the fallback, and threshold decisions must identify which counting mode was used.
- Preserves assistant tool-call messages together with all corresponding tool-result messages. Tool exchanges are pair-safe and must never be split into invalid or semantically orphaned history.
- Applies context reduction in order: prune older completed tool exchanges first, then compact eligible retained material only if pruning is insufficient. Permanent structured facts remain available through the dynamic prompt.
- Provider-native context management is optional and capability-gated. It may be used only when the selected provider/model explicitly supports the required API; portable local policy remains the fallback and no provider-specific feature is assumed.

## Donor code provenance

The `ModelContextPolicy` contract and any new symbols introduced to implement it are locally written for this project. They are not copied or adapted from repositories under `reference/`. Existing symbols retain their previously recorded provenance; ordinary LangChain/LangGraph or provider API use is black-box dependency use, not donor-code reuse.

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
