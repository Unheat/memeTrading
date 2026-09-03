# Execution Plan 07 — In-Process Local SEC Assessor

## Purpose

Make the completed `verify_sec_claim` path capable of generating its own constrained explanatory assessment while preserving its local-only boundary. Add one `llama-cpp-python` adapter that loads a manually provisioned GGUF model directly in process, receives only a claim plus retrieved local chunks, and returns the existing assessor mapping for verifier validation.

## Decision

Use `llama-cpp-python`, not Ollama, `llama-server`, a hosted model API, or an MCP model server. The Python bindings support local GGUF inference and JSON-schema-constrained chat output; running the model in process avoids a loopback HTTP exception to the verifier's no-network rule. `llama.cpp` supports GGUF local files and optional grammar/JSON constraints, but this application must never use its download-oriented `-hf` path. [llama-cpp-python JSON-schema mode](https://github.com/abetlen/llama-cpp-python) and [llama.cpp local GGUF documentation](https://github.com/ggml-org/llama.cpp) informed this dependency choice.

Model weights are not committed, downloaded, selected by the agent, or copied from a reference repository. A user/admin supplies a separately licensed, instruction-tuned GGUF file through an explicit existing path and model receipt (identity, SHA-256, license/source reference). The first real model is chosen only after hardware fit and fixture-quality evaluation; the code must remain model-family agnostic.

## Boundary

```text
retrieved case-local chunks
        |
        v
create_local_sec_assessor(config)
  validates existing GGUF file + immutable model receipt
        |
        v
in-process llama-cpp-python chat completion
  temperature 0 + JSON-schema response
        |
        v
proposed assessor mapping
        |
        v
existing verify_sec_claim()
  validates IDs and creates immutable SEC citations
```

- The adapter is not an agent, outer tool, MCP server, web service, or scheduler component.
- It does not receive filesystem paths for SEC source documents, prior conversation, social/news/market data, or arbitrary user context.
- It cannot call tools, fetch a model, inspect a URL, or make HTTP requests.
- `verify_sec_claim` remains the final citation/verdict contract validator; a syntactically valid model response is never sufficient by itself.

## Donor code provenance

No donor repository implementation is copied or adapted. `llama-cpp-python` is a normal black-box dependency. Its documented `Llama.create_chat_completion(..., response_format={"type": "json_object", "schema": ...})` API is used according to its official contract, not copied into project code.

## Required behavior

1. Define one immutable local-assessor configuration with model path, model identity, expected SHA-256, chat format, context window, GPU-layer setting, response-token cap, and timeout/cancellation boundary. All numeric defaults are named constants.
2. Reject missing, non-file, digest-mismatched, or unconfigured model artifacts before importing/loading the runtime. Never accept a URL, repository ID, `-hf` notation, or model-download instruction.
3. Load `llama_cpp.Llama` directly from the explicit GGUF path. Dependency/import/model-load failures become safe, structured unavailable errors; raw errors and local absolute paths do not reach an outer caller.
4. Build a bounded prompt containing only: verifier instruction, claim, allowed verdict vocabulary, output-field definitions, and each retrieved chunk's `chunk_id` plus text. State explicitly that cited IDs must come from the presented list; do not ask the model to write filing URLs, forms, dates, or quotations.
5. Use JSON Schema requiring the complete assessor mapping. Set deterministic generation settings and named context/output caps. Parse one response object; malformed JSON/schema output is a safe assessor failure.
6. Return only the proposed mapping expected by `verify_sec_claim`; do not construct `SECVerification`, `SecEvidence`, or source receipts in the model adapter.
7. Permit injection of a fake Llama factory/response for deterministic unit tests. Tests must run with networking disabled and no GGUF model installed.
8. Add one separately marked manual smoke command, run only after the user has provisioned a compatible local model. It must verify the output schema, receipt validation, and zero network attempts on a fixture corpus; do not make it a normal test dependency.

## Files expected during implementation

```text
doc/specs/sec/local_assessor.md
app/sec/local_assessor.py
tests/sec/test_local_assessor.py
requirements.txt
```

`app/sec/verifier.py` changes only if a test proves a narrow factory/configuration integration is needed. It must retain its injected-assessor contract and must not import `llama_cpp` directly.

## Execution steps

1. Re-read the official `llama-cpp-python` API and compatible installation guidance immediately before modifying dependencies. Confirm the JSON-schema API and platform build settings; do not infer them.
2. Write `doc/specs/sec/local_assessor.md` immediately before production code. Record the black-box dependency decision, configuration receipt, safe errors, prompt/input boundary, JSON schema, named caps, and exact test seams.
3. Create red unit tests with fake local model files and a fake Llama factory. Cover absent file, directory instead of file, digest mismatch, missing dependency, load failure, prompt containment, JSON-schema request, valid parsed mapping, malformed response, and networking disabled.
4. Run targeted tests and record expected red failures before creating `app/sec/local_assessor.py`.
5. Add the narrow direct-inference adapter and only the required `llama-cpp-python` dependency. Do not download weights or add a model to the repository.
6. Run targeted tests, then all project tests and compilation. Refresh the code graph and trace verifier integration.
7. Update the module spec and this plan with actual dependency version/build notes, test results, and manual-model smoke instructions. Do not claim a model-quality result until a user-provisioned model has passed fixture evaluation.

## Done checkpoint

With a manually provisioned, receipt-validated local GGUF model, the system can create a deterministic, JSON-schema-constrained proposed SEC assessment completely in process. With no model configured, it fails safely. In both cases, the existing verifier remains the only component that can produce cited `SECVerification` output.
