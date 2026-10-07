"""
Tests for embedding provider abstractions and vector normalization in SVANT Phase 2.
"""

from __future__ import annotations

import numpy as np
import pytest
from svant.core.embeddings import (
    EmbeddingProvider,
    MockEmbeddingProvider,
    normalize_vectors,
    get_embedding_provider,
)


def test_vector_normalization_1d():
    vec = np.array([3.0, 4.0], dtype=np.float32)
    normed = normalize_vectors(vec)
    assert np.isclose(np.linalg.norm(normed), 1.0)
    assert np.isclose(normed[0], 0.6)
    assert np.isclose(normed[1], 0.8)


def test_vector_normalization_2d():
    mat = np.array([[1.0, 0.0], [0.0, 5.0], [3.0, 4.0]], dtype=np.float32)
    normed = normalize_vectors(mat)
    norms = np.linalg.norm(normed, axis=1)
    assert np.allclose(norms, 1.0)


def test_vector_normalization_zero_vector():
    zero = np.zeros(4, dtype=np.float32)
    normed = normalize_vectors(zero)
    assert normed.shape == (4,)
    # Should not crash with NaN/inf
    assert not np.isnan(normed).any()


def test_mock_embedding_provider_dimension():
    provider = MockEmbeddingProvider(dimension=384)
    assert provider.dimension == 384
    assert provider.model_name == "mock-embedding-384"
    assert provider.is_available is True


def test_mock_embedding_provider_texts():
    provider = MockEmbeddingProvider(dimension=128)
    texts = [
        "Python virtual environments isolate dependencies.",
        "FAISS enables fast inner-product vector indexing.",
        "SQLite FTS5 provides full-text keyword retrieval.",
    ]
    embeddings = provider.embed_texts(texts)
    assert embeddings.shape == (3, 128)
    assert embeddings.dtype == np.float32

    # Check that each vector is unit-normalized
    norms = np.linalg.norm(embeddings, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-5)


def test_mock_embedding_provider_deterministic():
    provider = MockEmbeddingProvider(dimension=64)
    text = "Consistent query for deterministic testing"
    vec1 = provider.embed_query(text)
    vec2 = provider.embed_query(text)
    assert np.allclose(vec1, vec2)


def test_mock_embedding_query_cosine_similarity():
    provider = MockEmbeddingProvider(dimension=128)
    doc_vec = provider.embed_query("Local SQLite vector search")
    query_vec = provider.embed_query("Local SQLite vector search")
    different_vec = provider.embed_query("Completely unrelated baking recipe")

    # Exact match inner product should be ~ 1.0
    sim_exact = float(np.dot(doc_vec, query_vec))
    assert np.isclose(sim_exact, 1.0, atol=1e-5)

    # Different text should have different embedding
    assert not np.allclose(doc_vec, different_vec)


def test_get_embedding_provider_mock_factory():
    provider = get_embedding_provider(mock=True)
    assert isinstance(provider, EmbeddingProvider)
    assert provider.dimension == 384
