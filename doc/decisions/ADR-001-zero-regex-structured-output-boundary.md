# ADR-001: Zero-Regex Structured Output Boundary for Model Reasoning & Intent

## Status
Accepted

## Date
2026-10-18

## Context
In earlier iterations of the agent workflow, several components used regular expressions, substring matching (`any(k in s for k in ...)`), and word-list blacklists on natural language text and model responses. Examples included:
- Checking `"wide" in moat_rating` or `"CLEAN" in verdict` (which falsely matched negated phrases like `"no wide moat"` or `"UNCLEAN"`).
- Using word blacklists (`"NOW"`, `"TECH"`, `"BEST"`) to detect conversational noise, which inadvertently deleted valid NYSE/NASDAQ exchange ticker symbols like ServiceNow (`NOW`).
- Slicing markdown code fences via `.split("```json")[1]`, which crashed if the model output raw JSON or formatted markdown fences with trailing comments.
- Regex pattern matching on price targets and growth percentages, which misparsed discussions of tax rates or operating margins as growth numbers.

This violated our core architectural guideline in `AGENTS.md`: *"Never use regex pattern matching, substring searching, or hand-rolled heuristics on natural language user queries or LLM responses."*

## Decision
Enforce a strict architectural boundary between model reasoning and deterministic code execution:
1. **Schema-Constrained Structured Outputs**: All model-driven intent parsing, hypothesis decomposition, specialist analysis (forensics, moat, sector, thematic, bull, bear), and committee deliberations must use industry-standard structured outputs (`response_format` / Pydantic schemas via LangChain/LiteLLM `invoke_structured_model`).
2. **Exact Enum & Set Equality**: Categorical outputs must be typed as Pydantic `Literal` enums (e.g., `Literal["WIDE", "NARROW", "NONE"]`). Downstream business logic must test exact set membership (`verdict in CLEAN_FORENSIC_VERDICTS`), completely eliminating substring `in` checks.
3. **Lexical Exchange Symbol Invariants**: Replace ticker blacklists with structural invariants: an exchange ticker is valid if and only if it consists of 1 to 12 uppercase alphanumeric characters plus standard share-class delimiters (`.` and `-`), with zero whitespace.
4. **Resilient Multi-Tier JSON Parsing**: Replace string slicing with a multi-tier parser in `parse_llm_json_block`:
   - Tier 1: Direct JSON parse (`json.loads`).
   - Tier 2: Markdown fence extraction (````json ... ````).
   - Tier 3: Outermost bracket search (`{` to `}`).

## Alternatives Considered

### Retaining Hand-Rolled Substring Heuristics with Expanded Synonym Lists
- Pros: Simple to write initially; requires no schema validation.
- Cons: Extremely brittle to language variation, negation, phrasing nuance, and LLM temperature drift; fails quietly.
- Rejected: Unacceptable for institutional financial engineering and capital allocation.

### Unconstrained Free-Text Generation with Regex Post-Processing
- Pros: Allows the model complete freedom in its prose responses.
- Cons: High failure rate in downstream deterministic gates; prompts become cluttered with complex formatting instructions.
- Rejected: Violates determinism and testability requirements.

## Consequences
- Every agent node returns strongly-typed, schema-validated Pydantic artifacts.
- Zero false positives on ticker symbols (`NOW`, `TECH`, `FALLBACK` pass validation cleanly).
- Complete elimination of parsing crashes on malformed code fences.
- Backward-compatible test mocks must return dictionary structures conforming to Pydantic schemas.
