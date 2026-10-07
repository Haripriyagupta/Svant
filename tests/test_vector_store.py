"""
Tests for FAISS vector store abstraction in SVANT Phase 2.
"""

from __future__ import annotations

from pathlib import Path
import numpy as np
import pytest

from svant.core.vector_store import FAISSVectorStore, get_project_index_path
from svant.core.embeddings import normalize_vectors


def test_vector_store_init_and_count():
    store = FAISSVectorStore(dimension=16)
    assert store.dimension == 16
    assert store.count() == 0


def test_vector_store_add_and_search():
    store = FAISSVectorStore(dimension=4)

    # 3 distinct orthogonal vectors
    vecs = np.array([
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
    ], dtype=np.float32)
    ids = [101, 102, 103]

    added = store.add_vectors(ids, vecs)
    assert added == 3
    assert store.count() == 3

    # Query matching vector 101 exactly
    query = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    results = store.search(query, top_k=2)
    assert len(results) == 2
    assert results[0].vector_id == 101
    assert np.isclose(results[0].score, 1.0)
    # Second should have 0 score because orthogonal
    assert np.isclose(results[1].score, 0.0)


def test_vector_store_remove_vectors():
    store = FAISSVectorStore(dimension=4)
    vecs = np.array([
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
    ], dtype=np.float32)
    ids = [201, 202]

    store.add_vectors(ids, vecs)
    assert store.count() == 2

    removed = store.remove_vectors([201])
    assert removed == 1
    assert store.count() == 1

    # Search should no longer return 201
    query = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    results = store.search(query, top_k=5)
    assert len(results) == 1
    assert results[0].vector_id == 202


def test_vector_store_save_and_load(tmp_path: Path):
    index_file = tmp_path / "test_chunks.index"
    store = FAISSVectorStore(dimension=8, index_path=index_file)

    vecs = np.random.randn(5, 8).astype(np.float32)
    vecs = normalize_vectors(vecs)
    ids = [1, 2, 3, 4, 5]
    store.add_vectors(ids, vecs)
    assert store.count() == 5

    # Save to disk
    store.save()
    assert index_file.is_file()

    # Load in new store instance
    new_store = FAISSVectorStore(dimension=8, index_path=index_file)
    assert new_store.count() == 5

    # Search in restored store
    q = vecs[0]
    hits = new_store.search(q, top_k=1)
    assert len(hits) == 1
    assert hits[0].vector_id == 1
    assert np.isclose(hits[0].score, 1.0, atol=1e-5)


def test_vector_store_empty_search():
    store = FAISSVectorStore(dimension=4)
    query = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    assert store.search(query, top_k=10) == []


def test_vector_store_dimension_mismatch():
    store = FAISSVectorStore(dimension=8)
    bad_vecs = np.ones((2, 4), dtype=np.float32)
    with pytest.raises(ValueError, match="Vector shape mismatch"):
        store.add_vectors([1, 2], bad_vecs)
