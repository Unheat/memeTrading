# Module Spec — `app/agent/adversarial.py`

## Responsibility

Execute an air-gapped adversarial short-seller stress test against accumulated research evidence to eliminate confirmation bias.

## Public Contracts

### `AdversarialReport`
- `ticker: str` (non-empty uppercase)
- `falsifiable_objections: tuple[str, ...]` (minimum 4 explicit structural mechanisms)
- `numeric_kill_criteria: tuple[str, ...]` (minimum 2 explicit quantitative invalidation triggers)
- `bear_floor_price: float | None` (estimated downside price floor)
- `bear_thesis_summary: str` (core short-seller argument)

### `run_adversarial_red_team(state: InvestigationState, model: Any) -> dict[str, Any]`
- **Input**: Current `InvestigationState` with facts, evidence, and market context.
- **Process**: Formulates a clean-room prompt with `ADVERSARIAL_SYSTEM_PROMPT` and invokes `model` under strict isolation.
- **Output**: Dictionary updating `state["thesis_breakers"]` and `state["adversarial_report"]`.

## Donor Code Provenance

| Local symbol | Reuse type | Exact donor location | Deliberate changes |
| --- | --- | --- | --- |
| `app.agent.adversarial.ADVERSARIAL_SYSTEM_PROMPT` | adapted | `reference/investment-research/prompts/bear-adversarial.prompt.md:1-35` | Adapted into in-context prompt enforcing 4 falsifiable objections and 2 numeric kill criteria. |
| `app.agent.adversarial.AdversarialReport` | adapted | `reference/investment-research/schemas/bear-case.schema.json` | Python frozen dataclass for the bear report. |

## Acceptance Criteria
1. Air-gapped isolation: model prompt contains only facts, with zero visibility into optimistic draft language.
2. Returns at least 4 objections and 2 numeric kill triggers.
3. Parsing failure degrades gracefully to safe fallback kill triggers without crashing.
