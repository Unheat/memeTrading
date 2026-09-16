"""Case-local hybrid FAISS and BM25 retrieval for prepared SEC chunks."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any, Literal

import numpy as np

from app.sec.corpus import CorpusChunk


MAX_QUERY_CHARACTERS = 2000
MAX_CANDIDATES = 10
DEFAULT_TOP_K = 5
RRF_DENOMINATOR = 60
INDEX_FILENAME = "sec.faiss"
INDEX_MANIFEST_FILENAME = "sec-index-manifest.json"
CHUNKS_FILENAME = "chunks.jsonl"
PREPARATION_MANIFEST_FILENAME = "chunks-manifest.json"
INDEX_DIRECTORY = Path("sec") / "index"
VALID_ERROR_CODES = frozenset({"INVALID_INPUT", "MISSING_PREPARATION", "STALE_PREPARATION", "DEPENDENCY_UNAVAILABLE", "INVALID_VECTOR", "CORRUPT_INDEX", "STORAGE_FAILURE"})


@dataclass(frozen=True)
class RetrievalError:
    """Safe local retrieval failure.

    Attributes:
        code: Stable machine-readable failure class.
        message: Safe caller-facing explanation.
        retryable: Whether retrying later may succeed.
    """
    code: Literal["INVALID_INPUT", "MISSING_PREPARATION", "STALE_PREPARATION", "DEPENDENCY_UNAVAILABLE", "INVALID_VECTOR", "CORRUPT_INDEX", "STORAGE_FAILURE"]
    message: str
    retryable: bool

    def __post_init__(self) -> None:
        """Validate failure fields.

        Args: None.
        Returns: None.
        Raises: ValueError: If fields are invalid.
        """
        if self.code not in VALID_ERROR_CODES or not self.message.strip():
            raise ValueError("retrieval error is invalid")


@dataclass(frozen=True)
class IndexBuildResult:
    """Case-local index build success or safe failure."""
    index_path: Path | None = None
    error: RetrievalError | None = None

    def __post_init__(self) -> None:
        """Require one result branch.

        Args: None.
        Returns: None.
        Raises: ValueError: If branches are ambiguous.
        """
        if (self.index_path is None) == (self.error is None):
            raise ValueError("index build result is invalid")


@dataclass(frozen=True)
class RetrievedSecChunk:
    """One ranked local SEC chunk with retrieval audit data."""
    chunk: CorpusChunk
    dense_rank: int | None
    sparse_rank: int | None
    rrf_score: float
    rerank_score: float | None
    rerank_status: Literal["APPLIED", "NOT_APPLIED"]


@dataclass(frozen=True)
class RetrievalResult:
    """Retrieved SEC evidence candidates or safe failure."""
    results: tuple[RetrievedSecChunk, ...] = ()
    error: RetrievalError | None = None

    def __post_init__(self) -> None:
        """Require one result branch.

        Args: None.
        Returns: None.
        Raises: ValueError: If branches are ambiguous.
        """
        if (not self.results) == (self.error is None):
            raise ValueError("retrieval result is invalid")


def _failure(code: RetrievalError.code, message: str, retryable: bool) -> RetrievalError:
    """Create a validated retrieval error.

    Args:
        code: Stable error code.
        message: Safe explanation.
        retryable: Retry indicator.

    Returns:
        Validated error object.
    """
    return RetrievalError(code, message, retryable)


def _paths(directory: Path) -> tuple[Path, Path, Path, Path]:
    """Return fixed preparation and index artifact paths.

    Args:
        directory: Case directory.

    Returns:
        Chunks, preparation manifest, index, and index manifest paths.
    """
    index_directory = directory / INDEX_DIRECTORY
    return (index_directory / CHUNKS_FILENAME, index_directory / PREPARATION_MANIFEST_FILENAME, index_directory / INDEX_FILENAME, index_directory / INDEX_MANIFEST_FILENAME)


def _load_chunks(directory: Path) -> tuple[tuple[CorpusChunk, ...], dict[str, Any]]:
    """Load completed prepared chunks and their local manifest.

    Args:
        directory: Existing case directory.

    Returns:
        Validated chunks and preparation metadata.

    Raises:
        FileNotFoundError: If preparation artifacts are absent.
        ValueError: If artifacts are invalid.
    """
    chunks_path, preparation_path, _, _ = _paths(directory)
    metadata = json.loads(preparation_path.read_text(encoding="utf-8"))
    chunks = tuple(CorpusChunk.from_dict(json.loads(line)) for line in chunks_path.read_text(encoding="utf-8").splitlines() if line.strip())
    if not chunks or metadata.get("chunk_count") != len(chunks) or metadata.get("artifact") != CHUNKS_FILENAME:
        raise ValueError("prepared chunks are invalid")
    return chunks, metadata


def _vectors(raw_vectors: Sequence[Sequence[float]], expected_count: int) -> np.ndarray:
    """Validate and convert embeddings into finite float32 matrix.

    Args:
        raw_vectors: Caller-supplied local embeddings.
        expected_count: Required vector count.

    Returns:
        Two-dimensional finite float32 array.

    Raises:
        ValueError: If count, shape, dimension, or values are invalid.
    """
    vectors = np.asarray(raw_vectors, dtype="float32")
    if vectors.ndim != 2 or vectors.shape[0] != expected_count or vectors.shape[1] == 0 or not np.isfinite(vectors).all():
        raise ValueError("embedding vectors are invalid")
    return vectors


def _index_metadata(preparation: Mapping[str, Any], chunks: Sequence[CorpusChunk], dimension: int) -> dict[str, Any]:
    """Build JSON-safe immutable index identity metadata.

    Args:
        preparation: Current preparation manifest.
        chunks: Current ordered local chunks.
        dimension: Dense vector dimension.

    Returns:
        Index manifest data.
    """
    return {"corpus_id": preparation["corpus_id"], "document_sha256": preparation["document_sha256"], "chunk_ids": [chunk.chunk_id for chunk in chunks], "dimension": dimension}


def _atomic_faiss_write(index: Any, path: Path) -> None:
    """Atomically persist a CPU FAISS index.

    Args:
        index: Built FAISS index.
        path: Final case-local index path.

    Returns:
        None.
    """
    import faiss
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
        temporary_path = Path(temporary.name)
    try:
        faiss.write_index(index, str(temporary_path))
        os.replace(temporary_path, path)
    except OSError:
        temporary_path.unlink(missing_ok=True)
        raise


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    """Atomically persist one JSON artifact.

    Args:
        path: Final local JSON path.
        value: JSON-safe mapping.

    Returns:
        None.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as temporary:
        json.dump(value, temporary, sort_keys=True)
        temporary.write("\n")
        temporary_path = Path(temporary.name)
    try:
        os.replace(temporary_path, path)
    except OSError:
        temporary_path.unlink(missing_ok=True)
        raise


def build_sec_index(case_directory: Path, embedder: Callable[[list[str]], Sequence[Sequence[float]]]) -> IndexBuildResult:
    """Build a local FAISS index from prepared SEC chunks.

    Args:
        case_directory: Existing prepared case directory.
        embedder: Injected local text-to-vector callable.

    Returns:
        Local index path or safe build failure.
    """
    try:
        directory = Path(case_directory)
        chunks, preparation = _load_chunks(directory)
    except FileNotFoundError:
        return IndexBuildResult(error=_failure("MISSING_PREPARATION", "Local SEC chunks are unavailable.", False))
    except (OSError, ValueError, json.JSONDecodeError, KeyError, TypeError):
        return IndexBuildResult(error=_failure("STALE_PREPARATION", "Local SEC chunks are invalid or stale.", False))
    try:
        vectors = _vectors(embedder([chunk.text for chunk in chunks]), len(chunks))
    except (TypeError, ValueError):
        return IndexBuildResult(error=_failure("INVALID_VECTOR", "Local embedding vectors are invalid.", False))
    try:
        import faiss
        index = faiss.IndexFlatL2(vectors.shape[1])
        index.add(vectors)
        _, _, index_path, manifest_path = _paths(directory)
        _atomic_faiss_write(index, index_path)
        _atomic_json(manifest_path, _index_metadata(preparation, chunks, vectors.shape[1]))
        return IndexBuildResult(index_path=index_path)
    except ModuleNotFoundError:
        return IndexBuildResult(error=_failure("DEPENDENCY_UNAVAILABLE", "FAISS dependency is unavailable.", True))
    except OSError:
        return IndexBuildResult(error=_failure("STORAGE_FAILURE", "Local SEC index storage is unavailable.", True))
    except Exception:
        return IndexBuildResult(error=_failure("CORRUPT_INDEX", "Local SEC index could not be built.", False))


def search_sec_corpus(case_directory: Path, query: str, embed_query: Callable[[str], Sequence[float]], reranker: Callable[[str, Sequence[CorpusChunk]], Sequence[tuple[str, float]]] | None = None, top_k: int = DEFAULT_TOP_K) -> RetrievalResult:
    """Search one local SEC corpus with dense, BM25, RRF, and optional reranking.

    Args:
        case_directory: Existing indexed case directory.
        query: Narrow SEC claim or retrieval question.
        embed_query: Injected local query-to-vector callable.
        reranker: Optional local candidate scorer returning chunk-ID score pairs.
        top_k: Maximum final candidate count.

    Returns:
        Receipt-preserving ranked chunks or safe retrieval failure.
    """
    if not isinstance(query, str) or not query.strip() or len(query) > MAX_QUERY_CHARACTERS or not isinstance(top_k, int) or top_k < 1:
        return RetrievalResult(error=_failure("INVALID_INPUT", "Retrieval query or result limit is invalid.", False))
    try:
        directory = Path(case_directory)
        chunks, preparation = _load_chunks(directory)
        _, _, index_path, manifest_path = _paths(directory)
        metadata = json.loads(manifest_path.read_text(encoding="utf-8"))
        if metadata != _index_metadata(preparation, chunks, metadata["dimension"]):
            raise ValueError("index is stale")
        import faiss
        from rank_bm25 import BM25Okapi
        index = faiss.read_index(str(index_path))
        query_vector = _vectors([embed_query(query)], 1)
        if query_vector.shape[1] != metadata["dimension"]:
            return RetrievalResult(error=_failure("INVALID_VECTOR", "Query vector dimension is invalid.", False))
        candidate_count = min(MAX_CANDIDATES, len(chunks))
        _, dense_matrix = index.search(query_vector, candidate_count)
        dense_ids = [int(value) for value in dense_matrix[0] if 0 <= int(value) < len(chunks)]
        bm25 = BM25Okapi([chunk.text.lower().split() for chunk in chunks])
        sparse_ids = list(np.argsort(bm25.get_scores(query.lower().split()))[::-1][:candidate_count])
        ranks: dict[int, list[int | None]] = {}
        scores: dict[int, float] = {}
        for rank, chunk_id in enumerate(dense_ids, start=1):
            ranks.setdefault(chunk_id, [None, None])[0] = rank
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (RRF_DENOMINATOR + rank)
        for rank, chunk_id in enumerate(sparse_ids, start=1):
            ranks.setdefault(int(chunk_id), [None, None])[1] = rank
            scores[int(chunk_id)] = scores.get(int(chunk_id), 0.0) + 1.0 / (RRF_DENOMINATOR + rank)
        candidate_ids = sorted(scores, key=lambda item: (-scores[item], item))[:candidate_count]
        candidates = [chunks[item] for item in candidate_ids]
        rerank_scores: dict[str, float] = {}
        if reranker is not None:
            rerank_scores = dict(reranker(query, candidates))
            candidate_ids.sort(key=lambda item: (-rerank_scores.get(chunks[item].chunk_id, float("-inf")), -scores[item], item))
        results = tuple(RetrievedSecChunk(chunks[item], ranks[item][0], ranks[item][1], scores[item], rerank_scores.get(chunks[item].chunk_id), "APPLIED" if reranker else "NOT_APPLIED") for item in candidate_ids[:min(top_k, len(candidate_ids))])
        return RetrievalResult(results=results)
    except FileNotFoundError:
        return RetrievalResult(error=_failure("MISSING_PREPARATION", "Local SEC retrieval index is unavailable.", False))
    except ModuleNotFoundError:
        return RetrievalResult(error=_failure("DEPENDENCY_UNAVAILABLE", "Local retrieval dependency is unavailable.", True))
    except (TypeError, ValueError, json.JSONDecodeError, KeyError):
        return RetrievalResult(error=_failure("CORRUPT_INDEX", "Local SEC retrieval index is invalid or stale.", False))
    except Exception:
        return RetrievalResult(error=_failure("CORRUPT_INDEX", "Local SEC retrieval could not complete.", False))


def search_candidate_sec_corpus(
    case_directory: Path | str,
    candidate_id: str,
    query: str,
    embed_query: Callable[[str], Sequence[float]],
    reranker: Callable[[str, Sequence[CorpusChunk]], Sequence[tuple[str, float]]] | None = None,
    top_k: int = DEFAULT_TOP_K,
) -> RetrievalResult:
    """Search the isolated SEC corpus belonging specifically to one candidate company.

    Args:
        case_directory: Existing case directory path.
        candidate_id: Identifier of the candidate company whose corpus to search.
        query: Query string.
        embed_query: Embedder function.
        reranker: Optional reranker function.
        top_k: Max results.

    Returns:
        RetrievalResult for that candidate's isolated corpus.
    """
    directory = Path(case_directory)
    cand_dir = directory / "candidates" / candidate_id
    target_dir = cand_dir if cand_dir.exists() else directory
    return search_sec_corpus(
        case_directory=target_dir,
        query=query,
        embed_query=embed_query,
        reranker=reranker,
        top_k=top_k,
    )
