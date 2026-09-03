# Execution Plan 07 — Local Ollama SEC Assessor

## Purpose

Make the completed `verify_sec_claim` path capable of generating its own constrained explanatory assessment while preserving its local-only boundary. Adapt Ara's existing local Ollama model connection into one small SEC assessor adapter. It receives only a claim plus retrieved local chunks and returns the existing assessor mapping for verifier validation.

## Decision

Use local Ollama, matching Ara's working model engine, not a new `llama-cpp-python` runtime, a hosted model API, or an MCP model server. Ara's `reference/enterprise-agentic-rag-platform-ara/app/agent.py:31-43` uses `ChatOllama` with a local model name. We adapt only that connection pattern; we do not reuse Ara's global graph, generic chat state, query rewriting, Tavily fallback, or API/UI.

The adapter connects only to an explicit loopback endpoint (`http://127.0.0.1:11434` or `http://localhost:11434`) and a model that a user/admin has already pulled into the local Ollama runtime. This satisfies the SEC verifier's no-internet rule: loopback is a local process boundary, not an external service. The application never calls `ollama pull`, enables Ollama cloud, accepts a remote host, or selects a model itself. Ollama supports JSON-schema-constrained structured output, which is the needed assessor contract. [Ollama structured-output documentation](https://docs.ollama.com/capabilities/structured-outputs)

## Boundary

```text
retrieved case-local chunks
        |
        v
create_local_sec_assessor(config)
  validates loopback host + pre-pulled model name
        |
        v
local Ollama chat completion
  temperature 0 + JSON-schema response
        |
        v
proposed assessor mapping
        |
        v
existing verify_sec_claim()
  validates IDs and creates immutable SEC citations
```

- The adapter is not an agent, outer tool, MCP server, external web service, or scheduler component.
- It does not receive filesystem paths for SEC source documents, prior conversation, social/news/market data, or arbitrary user context.
- It cannot call tools, pull a model, inspect a URL, or make an HTTP request outside its validated loopback Ollama endpoint.
- `verify_sec_claim` remains the final citation/verdict contract validator; a syntactically valid model response is never sufficient by itself.

## Donor code provenance

| Local symbol | Reuse type | Exact donor location | Deliberate changes |
| --- | --- | --- | --- |
| `app.sec.local_assessor.create_local_sec_assessor` | adapted | `reference/enterprise-agentic-rag-platform-ara/app/agent.py:31-43`, `LLM_MODEL` and `llm` | Restrict to an explicit loopback host and pre-pulled model; return JSON-schema-constrained assessor mapping; remove global model singleton, web fallback, LangGraph state, and generic chat behavior. |

## Required behavior

1. Define one immutable local-assessor configuration with explicit Ollama model name, allowed loopback base URL, response-token cap, timeout/cancellation boundary, and a model receipt supplied by the user/admin. All numeric defaults are named constants.
2. Reject an absent model name, malformed base URL, non-loopback host, credentials, query/fragment path, or any cloud/remote endpoint before contacting Ollama. Never accept a pull/download instruction.
3. Adapt Ara's `ChatOllama` connection pattern using the official Ollama Python client or a minimal LangChain adapter, selected from current official documentation at implementation time. Dependency/connection/model-unavailable failures become safe structured unavailable errors; raw endpoint details do not reach an outer caller.
4. Build a bounded prompt containing only: verifier instruction, claim, allowed verdict vocabulary, output-field definitions, and each retrieved chunk's `chunk_id` plus text. State explicitly that cited IDs must come from the presented list; do not ask the model to write filing URLs, forms, dates, or quotations.
5. Use JSON Schema requiring the complete assessor mapping. Set deterministic generation settings and named context/output caps. Parse one response object; malformed JSON/schema output is a safe assessor failure.
6. Return only the proposed mapping expected by `verify_sec_claim`; do not construct `SECVerification`, `SecEvidence`, or source receipts in the model adapter.
7. Permit injection of a fake Ollama client/response for deterministic unit tests. Tests must block every non-loopback connection and require no local model installed.
8. Add one separately marked manual smoke command, run only after the user has started local Ollama and manually pulled a model. It must verify the output schema, receipt validation, and rejection of non-loopback configuration on a fixture corpus; do not make it a normal test dependency.

## Files expected during implementation

```text
doc/specs/sec/local_assessor.md
app/sec/local_assessor.py
tests/sec/test_local_assessor.py
requirements.txt
```

`app/sec/verifier.py` changes only if a test proves a narrow factory/configuration integration is needed. It must retain its injected-assessor contract and must not import the Ollama client directly.

## Execution steps

1. Re-read the official Ollama structured-output and Python-client API immediately before modifying dependencies. Confirm the JSON-schema request, base URL configuration, and timeout behavior; do not infer them.
2. Write `doc/specs/sec/local_assessor.md` immediately before production code. Record Ara's exact adapted connection provenance, loopback-only configuration, safe errors, prompt/input boundary, JSON schema, named caps, and exact test seams.
3. Create red unit tests with a fake Ollama client. Cover absent model name, malformed/remote URL rejection, missing dependency, local connection failure, prompt containment, JSON-schema request, valid parsed mapping, malformed response, and non-loopback network blocking.
4. Run targeted tests and record expected red failures before creating `app/sec/local_assessor.py`.
5. Add the narrow Ollama adapter and only the required official client dependency. Do not pull a model or add model weights to the repository.
6. Run targeted tests, then all project tests and compilation. Refresh the code graph and trace verifier integration.
7. Update the module spec and this plan with actual dependency version/build notes, test results, and manual-model smoke instructions. Do not claim a model-quality result until a user-provisioned model has passed fixture evaluation.

## Done checkpoint

With a manually pre-pulled model running in local Ollama, the system can create a deterministic, JSON-schema-constrained proposed SEC assessment through an allowed loopback connection. With no model configured/running or a remote endpoint requested, it fails safely. In both cases, the existing verifier remains the only component that can produce cited `SECVerification` output.
