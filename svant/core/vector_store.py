"""
FAISS Vector Store abstraction for SVANT Phase 2.
Manages persistent, high-performance CPU vector indexing using IndexIDMap2 + IndexFlatIP.
Stores only vectors and 64-bit vector IDs. Authoritative metadata resides in SQLite.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional, Tuple

import faiss
import numpy as np

from svant.config import settings
from svant.logger import get_logger

logger = get_logger("svant.core.vector_store")


class VectorSearchResult:
    """Vector search hit representation."""

    def __init__(self, vector_id: int, score: float) -> None:
        self.vector_id = int(vector_id)
        self.score = float(score)

    def __repr__(self) -> str:
        return f"VectorSearchResult(vector_id={self.vector_id}, score={self.score:.4f})"


class FAISSVectorStore:
    """
    CPU-only FAISS index manager with explicit ID mapping.
    Uses IndexIDMap2 wrapping IndexFlatIP for cosine similarity on unit-normalized vectors.
    """

    def __init__(self, dimension: int, index_path: Optional[Path | str] = None) -> None:
        self.dimension = int(dimension)
        self.index_path = Path(index_path).resolve() if index_path else None
        self._index: Optional[faiss.IndexIDMap2] = None

        if self.index_path and self.index_path.is_file():
            self.load()
        else:
            self.reset()

    def reset(self) -> None:
        """Initialize an empty FAISS index."""
        sub_index = faiss.IndexFlatIP(self.dimension)
        self._index = faiss.IndexIDMap2(sub_index)
        logger.debug(f"Created new empty FAISS index with dimension {self.dimension}")

    def add_vectors(self, vector_ids: np.ndarray | List[int], vectors: np.ndarray) -> int:
        """
        Add batch of vectors with corresponding 64-bit integer IDs.
        Vectors must be float32, 2D array of shape (N, dimension).
        """
        if len(vector_ids) == 0:
            return 0

        ids_array = np.ascontiguousarray(np.array(vector_ids, dtype=np.int64))
        vecs_array = np.ascontiguousarray(np.array(vectors, dtype=np.float32))

        if vecs_array.ndim != 2 or vecs_array.shape[1] != self.dimension:
            raise ValueError(
                f"Vector shape mismatch: expected (_, {self.dimension}), got {vecs_array.shape}"
            )

        if len(ids_array) != vecs_array.shape[0]:
            raise ValueError(
                f"Count mismatch: {len(ids_array)} IDs provided for {vecs_array.shape[0]} vectors"
            )

        assert self._index is not None
        self._index.add_with_ids(vecs_array, ids_array)
        logger.debug(f"Added {len(ids_array)} vectors to FAISS index. Total vectors: {self.count()}")
        return len(ids_array)

    def remove_vectors(self, vector_ids: List[int]) -> int:
        """Remove specific vector IDs from the index."""
        if not vector_ids:
            return 0

        assert self._index is not None
        ids_array = np.ascontiguousarray(np.array(vector_ids, dtype=np.int64))
        try:
            removed = self._index.remove_ids(ids_array)
            logger.debug(f"Removed {removed} vectors from FAISS index. Remaining: {self.count()}")
            return removed
        except Exception as e:
            logger.warning(f"Error removing IDs {vector_ids} from FAISS index: {e}")
            return 0

    def search(self, query_vector: np.ndarray, top_k: int = 10) -> List[VectorSearchResult]:
        """
        Query nearest neighbors using inner product (cosine similarity).
        Query vector can be 1D or 2D (1, dimension).
        """
        if self.count() == 0:
            return []

        q_vec = np.ascontiguousarray(np.array(query_vector, dtype=np.float32))
        if q_vec.ndim == 1:
            q_vec = q_vec.reshape(1, -1)

        if q_vec.shape[1] != self.dimension:
            raise ValueError(
                f"Query dimension {q_vec.shape[1]} does not match index dimension {self.dimension}"
            )

        k = min(top_k, self.count())
        assert self._index is not None
        distances, indices = self._index.search(q_vec, k)

        results: List[VectorSearchResult] = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx != -1:  # FAISS returns -1 for unpopulated slots
                results.append(VectorSearchResult(vector_id=int(idx), score=float(dist)))

        return results

    def count(self) -> int:
        """Total vectors stored in index."""
        return self._index.ntotal if self._index is not None else 0

    def save(self, target_path: Optional[Path | str] = None) -> Path:
        """Persist index to disk."""
        path = Path(target_path).resolve() if target_path else self.index_path
        if not path:
            raise ValueError("No path specified to save FAISS index.")

        path.parent.mkdir(parents=True, exist_ok=True)
        assert self._index is not None
        faiss.write_index(self._index, str(path))
        self.index_path = path
        logger.debug(f"Persisted FAISS index ({self.count()} vectors) to '{path}'")
        return path

    def load(self, source_path: Optional[Path | str] = None) -> None:
        """Load index from disk."""
        path = Path(source_path).resolve() if source_path else self.index_path
        if not path or not path.is_file():
            raise FileNotFoundError(f"FAISS index file not found at '{path}'")

        try:
            loaded_index = faiss.read_index(str(path))
            if loaded_index.d != self.dimension:
                raise ValueError(
                    f"Index dimension mismatch: loaded {loaded_index.d}, expected {self.dimension}"
                )
            # Ensure it is an IndexIDMap2
            if not isinstance(loaded_index, faiss.IndexIDMap2):
                loaded_index = faiss.IndexIDMap2(loaded_index)
            self._index = loaded_index
            self.index_path = path
            logger.info(f"Loaded FAISS index with {self.count()} vectors from '{path}'")
        except Exception as e:
            logger.error(f"Failed to load FAISS index from '{path}': {e}")
            raise


def get_project_index_path(project_id: str) -> Path:
    """Return canonical path to FAISS index for a project under D:\\SVANTData\\indexes."""
    indexes_dir = Path(settings.indexes_dir).resolve()
    return indexes_dir / project_id / "chunks.index"
