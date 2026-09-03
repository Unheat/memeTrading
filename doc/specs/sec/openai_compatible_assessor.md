# Module Spec — `app/sec/openai_compatible_assessor.py`

## Status

Completed on 2026-09-03. Seven red tests ran before this module was created.

## Responsibility

Create one injected assessor callable for `verify_sec_claim`. It uses the official OpenAI Python client against one approved HTTPS OpenAI-compatible provider endpoint. It receives only a claim and the retrieved SEC chunks already selected by local retrieval. It asks the model for the existing structured assessor mapping; `app.sec.verifier` remains responsible for final receipt and verdict validation.

## Public contracts

### `OpenAICompatibleAssessorConfig`

An immutable configuration contains `base_url`, `api_key`, `model`, `approved_base_urls`, and bounded request settings. The base URL must be HTTPS, contain no credentials, query, or fragment, and exactly match one deployment-approved URL. The model and key must be non-empty. Numeric limits are named constants.

### `create_openai_compatible_sec_assessor(config, client=None)`

Returns a callable matching `app.sec.verifier.Assessor`. `client` is an optional fake OpenAI-compatible client injection seam for deterministic tests. With no injected client, the function initializes the black-box OpenAI Python client with the approved URL, key, and timeout; it does not issue a request while being created.

On each call the returned assessor:

1. Builds one bounded prompt from only the verifier instruction, claim, allowed verdicts/output fields, and each retrieved chunk's `chunk_id` and text.
2. Calls Chat Completions with a strict JSON Schema response format. It does **not** send a `tools` argument, an MCP definition, URLs, filesystem paths, other research results, or prior conversation.
3. Parses one JSON object and returns the mapping expected by `verify_sec_claim`.
4. Raises `AssessorUnavailableError` for provider/dependency/authentication/timeout failures. It raises `ValueError` for an absent or malformed model response.

### `AssessorUnavailableError`

`app.sec.verifier` provides this exception for injected assessors to report a retryable availability failure without exposing provider details. `verify_sec_claim` maps it to safe `ASSESSOR_UNAVAILABLE`; no raw exception or endpoint reaches the caller.

## Constraints

- The only permitted network operation is the explicit Chat Completions request to an approved provider endpoint.
- Provider capability is deployment responsibility: the selected model/provider must support strict JSON-schema response formatting. OpenRouter is an example, not a dependency or hard-coded default.
- The case stores provider base URL, model identifier, and inference time separately when an outer runner invokes this capability; this narrow adapter does not write case artifacts.
- No donor code is copied or adapted. The OpenAI Python SDK is a black-box dependency.

## Donor code provenance

No donor code is copied or adapted in this module. Ara's `reference/enterprise-agentic-rag-platform-ara/app/agent.py:31-43` local Ollama setup was considered and deliberately rejected because this project uses hosted OpenAI-compatible providers.

## Tests

`tests/sec/test_openai_compatible_assessor.py` must use a fake client and must never issue a real network request. It covers configuration rejection, prompt containment, strict schema shape, absence of tools, parsing, provider failure, and malformed model content. `tests/sec/test_verifier.py` must confirm that `AssessorUnavailableError` becomes the safe retryable verifier error.

## Execution record

Initial red run: `pytest tests/sec/test_openai_compatible_assessor.py tests/sec/test_verifier.py -q` produced seven expected failures because the adapter and `AssessorUnavailableError` did not yet exist. The implementation adds only the OpenAI-compatible adapter, the neutral availability error, and the `openai>=1.0,<3` black-box dependency. It does not make a provider request during construction or during automated tests.

Final verification: OpenAI Python SDK 2.54.0 installed successfully; 45 project tests passed; and `python3 -m compileall -q app` passed. No provider smoke request was run because no approved provider credential or model was supplied.
