# Execution Plan 07 — OpenRouter SEC Assessor

## Purpose

Make the completed `verify_sec_claim` path capable of generating its own constrained explanatory assessment while preserving its case-local retrieval boundary. Add one small OpenRouter assessor adapter. It receives only a claim plus retrieved local chunks and returns the existing assessor mapping for verifier validation.

## Decision

Use OpenRouter through its standard OpenAI-compatible API, not Ollama, a self-hosted model runtime, or an MCP model server. This is a black-box API dependency, not copied donor code. Ara's `reference/enterprise-agentic-rag-platform-ara/app/agent.py:31-43` is deliberately not reused because its `ChatOllama` connection requires the local server this project does not want to host. We do not reuse Ara's global graph, generic chat state, query rewriting, Tavily fallback, or API/UI.

The adapter calls the fixed OpenRouter API base URL with an `OPENROUTER_API_KEY` and explicit `OPENROUTER_MODEL` supplied at deployment. It sends no `tools` parameter or provider/server-side tool configuration. The verifier's no-internet rule is refined here: it prohibits external retrieval, downloads, and application tools, but permits the deliberate outbound inference request containing the presented local excerpts. OpenRouter supports JSON-schema-constrained structured output on compatible models; deployment must select one and require strict schema adherence. [OpenRouter structured-output documentation](https://openrouter.ai/docs/guides/features/structured-outputs)

## Boundary

```text
retrieved case-local chunks
        |
        v
create_openrouter_sec_assessor(config)
  validates explicit provider key + model name
        |
        v
OpenRouter structured chat completion
  temperature 0 + JSON-schema response
        |
        v
proposed assessor mapping
        |
        v
existing verify_sec_claim()
  validates IDs and creates immutable SEC citations
```

- The adapter is not an agent, outer tool, MCP server, external retrieval service, or scheduler component.
- It does not receive filesystem paths for SEC source documents, prior conversation, social/news/market data, or arbitrary user context.
- It cannot call application tools, inspect a URL, retrieve documents, or download content. Its only network operation is the explicit OpenRouter inference request.
- `verify_sec_claim` remains the final citation/verdict contract validator; a syntactically valid model response is never sufficient by itself.

## Donor code provenance

| Local symbol | Reuse type | Exact donor location | Deliberate changes |
| --- | --- | --- | --- |
| Module scope | locally written | N/A | No donor code is copied or adapted. OpenRouter's OpenAI-compatible client is used as a black-box dependency. Ara's Ollama adapter was considered and rejected because it requires a local model server. |

## Required behavior

1. Define one immutable assessor configuration with explicit OpenRouter model name, response-token cap, timeout/cancellation boundary, and case receipt metadata. All numeric defaults are named constants.
2. Reject an absent API key or model name before contacting the provider. Use only the fixed OpenRouter base URL in the MVP; do not accept arbitrary provider endpoints or a model-download instruction.
3. Use the official OpenAI Python client pointed at OpenRouter's OpenAI-compatible base URL. Dependency, authentication, provider, model-unavailable, and timeout failures become safe structured unavailable errors; raw provider details do not reach an outer caller.
4. Build a bounded prompt containing only: verifier instruction, claim, allowed verdict vocabulary, output-field definitions, and each retrieved chunk's `chunk_id` plus text. State explicitly that cited IDs must come from the presented list; do not ask the model to write filing URLs, forms, dates, or quotations.
5. Use JSON Schema requiring the complete assessor mapping, strict schema adherence, and no `tools` parameter. Set deterministic generation settings and named context/output caps. Parse one response object; malformed JSON/schema output is a safe assessor failure.
6. Return only the proposed mapping expected by `verify_sec_claim`; do not construct `SECVerification`, `SecEvidence`, or source receipts in the model adapter.
7. Permit injection of a fake OpenAI-compatible client/response for deterministic unit tests. Tests require no API key and make no network request.
8. Add one separately marked manual smoke command, run only when a user has supplied an OpenRouter key and selected a structured-output-compatible model. It must verify the output schema and receipt validation on a fixture corpus; do not make it a normal test dependency.

## Files expected during implementation

```text
doc/specs/sec/openrouter_assessor.md
app/sec/openrouter_assessor.py
tests/sec/test_openrouter_assessor.py
requirements.txt
```

`app/sec/verifier.py` changes only if a test proves a narrow factory/configuration integration is needed. It must retain its injected-assessor contract and must not import the OpenRouter client directly.

## Execution steps

1. Re-read the official OpenRouter OpenAI-compatible, structured-output, and tool-calling documentation immediately before modifying dependencies. Confirm the JSON-schema request, no-tools request shape, base URL, and timeout behavior; do not infer them.
2. Write `doc/specs/sec/openrouter_assessor.md` immediately before production code. Record the black-box dependency boundary, OpenRouter-only configuration, safe errors, prompt/input boundary, JSON schema, named caps, request receipt, and exact test seams.
3. Create red unit tests with a fake OpenAI-compatible client. Cover absent key/model name, missing dependency, provider connection failure, prompt containment, JSON-schema request, absence of tools, valid parsed mapping, and malformed response.
4. Run targeted tests and record expected red failures before creating `app/sec/openrouter_assessor.py`.
5. Add the narrow OpenRouter adapter and only the required official client dependency. Do not add local model runtimes or model weights to the repository.
6. Run targeted tests, then all project tests and compilation. Refresh the code graph and trace verifier integration.
7. Update the module spec and this plan with actual dependency version/build notes, test results, and manual-provider smoke instructions. Do not claim a model-quality result until a user-provisioned model has passed fixture evaluation.

## Done checkpoint

With a configured OpenRouter API key and structured-output-compatible model, the system can create a deterministic, JSON-schema-constrained proposed SEC assessment without hosting Ollama. With no API key/model configured or provider call failure, it fails safely. In both cases, the existing verifier remains the only component that can produce cited `SECVerification` output.
