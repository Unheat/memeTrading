# Module Spec — `app/sec/identity.py` and `app/sec/embeddings.py`

## Responsibility

1. `app/sec/identity.py`: Standardized compliant SEC User-Agent header initialization.
2. `app/sec/embeddings.py`: Local and API embedding engine for SEC RAG indexing and claim verification.

## Public Contracts

### `app/sec/identity.py`
- `ensure_sec_identity(custom_identity: str | None = None) -> str`:
  - Priority order: `custom_identity` -> `SEC_USER_AGENT` env -> `EDGAR_IDENTITY` env -> `"MemeTradingResearchAgent research@memetrading.internal"`.
  - Sets `os.environ["SEC_USER_AGENT"]` and `os.environ["EDGAR_IDENTITY"]`.
  - Invokes `edgar.set_identity()` if `edgar` is available.
  - Returns the active compliant identity string.

### `app/sec/embeddings.py`
- `get_sec_embedder() -> Callable[[list[str]], list[list[float]]]`:
  - Returns a text-to-vector list embedder.
  - If `OPENAI_API_KEY` is set, uses OpenAI `text-embedding-3-small`.
  - Otherwise, uses a deterministic 128-dimensional normalized term-hash vectorizer (zero network, fast, deterministic).
- `get_sec_query_embedder() -> Callable[[str], list[float]]`:
  - Returns a single query-to-vector embedder.

## Donor Code Provenance

| Local symbol | Reuse type | Exact donor location | Deliberate changes |
| --- | --- | --- | --- |
| `app.sec.identity.ensure_sec_identity` | adapted | `reference/edgartools/edgar/settings.py:109-126` | Added safe fallback string and dual environment variable synchronization. |
| `app.sec.embeddings._hash_embed` | locally written | N/A | Deterministic 128d hash embedding for offline testing and keyless fallback. |
