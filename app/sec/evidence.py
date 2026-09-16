"""Read-only outer-agent adapters for the existing local SEC corpus.

This module is locally written. It exposes compact citation receipts over prepared
chunks and delegates retrieval to the existing FAISS/BM25/RRF implementation.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Sequence

from app.sec.corpus import CorpusChunk
from app.sec.retrieval import RetrievedSecChunk, RetrievalResult, search_sec_corpus

MAX_EXCERPT_CHARACTERS = 1_500


def retrieved_chunk_receipt(result: RetrievedSecChunk, candidate_id: str | None = None) -> dict[str, Any]:
    """Convert one ranked chunk into a bounded model-visible citation receipt.

    Args:
        result: Existing hybrid-retrieval result.
        candidate_id: Optional candidate workspace owner.

    Returns:
        JSON-safe compact receipt with retrieval audit fields.
    """
    chunk = result.chunk
    receipt: dict[str, Any] = {
        "chunk_id": chunk.chunk_id,
        "accession": chunk.accession,
        "form": chunk.form,
        "filing_date": chunk.filing_date.isoformat(),
        "document_name": chunk.document_name,
        "source_url": chunk.source_url,
        "relative_path": chunk.relative_path,
        "start_offset": chunk.start_offset,
        "end_offset": chunk.end_offset,
        "excerpt": chunk.text[:MAX_EXCERPT_CHARACTERS],
        "excerpt_truncated": len(chunk.text) > MAX_EXCERPT_CHARACTERS,
        "dense_rank": result.dense_rank,
        "sparse_rank": result.sparse_rank,
        "rrf_score": result.rrf_score,
        "rerank_score": result.rerank_score,
        "rerank_status": result.rerank_status,
    }
    if candidate_id:
        receipt["candidate_id"] = candidate_id
    return receipt


def search_sec_evidence(
    case_directory: Path | str,
    query: str,
    embed_query: Callable[[str], Sequence[float]],
    candidate_id: str | None = None,
    top_k: int = 5,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Search an indexed SEC corpus and return compact source receipts.

    Args:
        case_directory: Root or candidate-local case directory.
        query: Exploratory filing question.
        embed_query: Existing query embedding callable.
        candidate_id: Optional candidate owner label.
        top_k: Bounded result count.

    Returns:
        Receipt list and optional structured retrieval error.
    """
    directory = Path(case_directory)
    index_file = directory / "sec" / "index" / "sec.faiss"
    if not index_file.exists():
        from app.sec.corpus import prepare_sec_corpus
        from app.sec.embeddings import get_sec_embedder
        from app.sec.retrieval import build_sec_index
        prep_res = prepare_sec_corpus(directory)
        if prep_res.error is None:
            build_sec_index(directory, embedder=get_sec_embedder())

    result: RetrievalResult = search_sec_corpus(directory, query, embed_query, top_k=top_k)
    if result.error:
        return [], {"code": result.error.code, "message": result.error.message, "retryable": result.error.retryable}
    return [retrieved_chunk_receipt(item, candidate_id) for item in result.results], None


def read_sec_evidence(
    case_directory: Path | str,
    chunk_ids: Sequence[str],
    candidate_id: str | None = None,
    context_characters: int = 300,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Read exact prepared chunks with bounded neighboring context.

    Args:
        case_directory: Indexed case or candidate directory.
        chunk_ids: Existing chunk IDs selected from search results.
        candidate_id: Optional candidate owner label.
        context_characters: Text context taken from adjacent chunk boundaries.

    Returns:
        Exact chunk receipts and an optional safe error.
    """
    if not chunk_ids or any(not isinstance(item, str) or not item.strip() for item in chunk_ids):
        return [], {"code": "INVALID_INPUT", "message": "chunk_ids must contain one or more chunk identifiers.", "retryable": False}
    path = Path(case_directory) / "sec" / "index" / "chunks.jsonl"
    try:
        chunks = [CorpusChunk.from_dict(json.loads(line)) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, ValueError, json.JSONDecodeError):
        return [], {"code": "MISSING_PREPARATION", "message": "Local SEC chunks are unavailable.", "retryable": False}
    index = {chunk.chunk_id: position for position, chunk in enumerate(chunks)}
    missing = [item for item in chunk_ids if item not in index]
    if missing:
        return [], {"code": "NOT_FOUND", "message": f"Requested SEC chunks are unavailable: {', '.join(missing[:3])}.", "retryable": False}
    receipts: list[dict[str, Any]] = []
    for chunk_id in chunk_ids:
        position = index[chunk_id]
        chunk = chunks[position]
        before = chunks[position - 1].text[-context_characters:] if position and chunks[position - 1].accession == chunk.accession else ""
        after = chunks[position + 1].text[:context_characters] if position + 1 < len(chunks) and chunks[position + 1].accession == chunk.accession else ""
        receipt: dict[str, Any] = {
            "chunk_id": chunk.chunk_id,
            "accession": chunk.accession,
            "form": chunk.form,
            "filing_date": chunk.filing_date.isoformat(),
            "document_name": chunk.document_name,
            "source_url": chunk.source_url,
            "start_offset": chunk.start_offset,
            "end_offset": chunk.end_offset,
            "text": chunk.text,
            "preceding_context": before,
            "following_context": after,
        }
        if candidate_id:
            receipt["candidate_id"] = candidate_id
        receipts.append(receipt)
    return receipts, None
