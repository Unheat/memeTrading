"""Tests for SEC RAG embedding engine."""
import os
from unittest.mock import patch, MagicMock
import pytest
from app.sec.embeddings import get_sec_embedder, get_sec_query_embedder, _hash_embed_text


def test_hash_embed_text_deterministic():
    v1 = _hash_embed_text("Micron DDR5 gross margin expansion")
    v2 = _hash_embed_text("Micron DDR5 gross margin expansion")
    assert v1 == v2
    assert len(v1) == 128
    assert all(isinstance(x, float) for x in v1)

    # Different text yields different vector
    v3 = _hash_embed_text("Completely unrelated pharmaceutical drug trial")
    assert v1 != v3


def test_get_sec_embedder_offline_fallback():
    with patch.dict("os.environ", {}, clear=True):
        embedder = get_sec_embedder()
        vectors = embedder(["Text A", "Text B"])
        assert len(vectors) == 2
        assert len(vectors[0]) == 128
        assert len(vectors[1]) == 128


def test_get_sec_query_embedder_offline_fallback():
    with patch.dict("os.environ", {}, clear=True):
        query_embedder = get_sec_query_embedder()
        vector = query_embedder("What is gross margin?")
        assert len(vector) == 128
        assert isinstance(vector, list)
