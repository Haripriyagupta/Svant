"""
Embedding service abstraction for SVANT Phase 2.
Provides CPU-friendly local embeddings and deterministic test mocks.
Vectors are unit-normalized to support FAISS inner product (cosine similarity).
"""

from __future__ import annotations

import hashlib
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional

import numpy as np

from svant.config import settings
from svant.logger import get_logger

logger = get_logger("svant.core.embeddings")


def normalize_vectors(vectors: np.ndarray) -> np.ndarray:
    """L2-normalize vectors so inner product is identical to cosine similarity."""
    if vectors.ndim == 1:
        norm = np.linalg.norm(vectors)
        if norm > 0:
            return vectors / norm
        return vectors

    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vectors / norms


class EmbeddingProvider(ABC):
    """Abstract interface for text embedding models."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Vector embedding dimension."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> int:
        """Name or identifier of the embedding model."""
        pass

    @abstractmethod
    def embed_texts(self, texts: List[str]) -> np.ndarray:
        """Generate normalized embeddings for a batch of documents."""
        pass

    @abstractmethod
    def embed_query(self, query: str) -> np.ndarray:
        """Generate normalized embedding for a search query."""
        pass

    @property
    def is_available(self) -> bool:
        """Check if model engine is ready for inference."""
        return True


class MockEmbeddingProvider(EmbeddingProvider):
    """
    Deterministic pseudo-embedding provider for fast, offline unit testing.
    Generates repeatable unit-normalized vectors without downloading models.
    """

    def __init__(self, dimension: int = 384, model_name: str = "mock-embedding-384") -> None:
        self._dim = dimension
        self._model_name = model_name

    @property
    def dimension(self) -> int:
        return self._dim

    @property
    def model_name(self) -> str:
        return self._model_name

    def _hash_to_vector(self, text: str) -> np.ndarray:
        # Generate repeatable pseudo-vector using MD5 & SHA256 bytes
        vec = np.zeros(self._dim, dtype=np.float32)
        words = text.lower().split()
        if not words:
            vec[0] = 1.0
            return vec

        for w in words:
            h = hashlib.sha256(w.encode("utf-8")).digest()
            for i in range(min(self._dim, len(h) * 4)):
                byte_idx = (i // 4) % len(h)
                shift = (i % 4) * 8
                val = ((h[byte_idx] >> (shift % 8)) & 0xFF) - 128
                vec[i % self._dim] += float(val) / 128.0

        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        else:
            vec[0] = 1.0
        return vec

    def embed_texts(self, texts: List[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, self._dim), dtype=np.float32)
        matrix = np.vstack([self._hash_to_vector(t) for t in texts])
        return normalize_vectors(matrix)

    def embed_query(self, query: str) -> np.ndarray:
        vec = self._hash_to_vector(query)
        return normalize_vectors(vec)


class LocalEmbeddingProvider(EmbeddingProvider):
    """
    Lightweight, CPU-only local embedding provider using FastEmbed (ONNX Runtime).
    Default model: 'BAAI/bge-small-en-v1.5' (384 dimensions, ~67-130 MB disk footprint).
    Stores model weights outside Git repository under D:\\SVANTData\\models.
    """

    def __init__(
        self,
        model_name: Optional[str] = None,
        cache_dir: Optional[Path | str] = None,
        batch_size: Optional[int] = None,
    ) -> None:
        self._model_name = model_name or settings.embedding_model
        raw_cache = cache_dir or settings.models_dir
        self.cache_dir = Path(raw_cache).resolve()
        self.batch_size = batch_size or settings.embedding_batch_size
        self._model_instance = None
        self._dimension: Optional[int] = None

    def _ensure_model(self) -> None:
        """Lazy load the ONNX TextEmbedding model."""
        if self._model_instance is not None:
            return

        try:
            from fastembed import TextEmbedding
        except ImportError as e:
            logger.error("fastembed package not installed. Run: pip install fastembed")
            raise RuntimeError(
                "fastembed is required for local embeddings. Please ensure it is installed in the virtual environment."
            ) from e

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Loading local embedding model '{self._model_name}' from cache '{self.cache_dir}'")
        try:
            self._model_instance = TextEmbedding(
                model_name=self._model_name,
                cache_dir=str(self.cache_dir),
            )
            # Discover dimension via a probe embedding
            probe = list(self._model_instance.embed(["probe"]))
            self._dimension = len(probe[0])
            logger.info(f"Local embedding model loaded successfully. Dimension: {self._dimension}")
        except Exception as err:
            logger.error(f"Failed to load embedding model '{self._model_name}': {err}")
            raise

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            self._ensure_model()
        return self._dimension or 384

    @property
    def model_name(self) -> str:
        return self._model_name

    def embed_texts(self, texts: List[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, self.dimension), dtype=np.float32)

        self._ensure_model()
        assert self._model_instance is not None

        try:
            raw_embeddings = list(self._model_instance.embed(texts, batch_size=self.batch_size))
            matrix = np.array(raw_embeddings, dtype=np.float32)
            return normalize_vectors(matrix)
        except Exception as e:
            logger.error(f"Error during batch text embedding: {e}")
            raise

    def embed_query(self, query: str) -> np.ndarray:
        clean_query = query.strip()
        if not clean_query:
            clean_query = " "

        self._ensure_model()
        assert self._model_instance is not None

        try:
            # Query embedding
            if hasattr(self._model_instance, "query_embed"):
                raw = list(self._model_instance.query_embed([clean_query]))[0]
            else:
                raw = list(self._model_instance.embed([clean_query]))[0]
            vec = np.array(raw, dtype=np.float32)
            return normalize_vectors(vec)
        except Exception as e:
            logger.error(f"Error during query embedding: {e}")
            raise


# Provider instance cache
_active_provider: Optional[EmbeddingProvider] = None


def get_embedding_provider(
    provider_type: Optional[str] = None,
    mock: bool = False,
    cache_dir: Optional[Path | str] = None,
) -> EmbeddingProvider:
    """Factory retrieving the configured embedding provider."""
    global _active_provider
    if mock:
        return MockEmbeddingProvider()

    if _active_provider is None or provider_type is not None:
        if provider_type == "mock":
            _active_provider = MockEmbeddingProvider()
        else:
            _active_provider = LocalEmbeddingProvider(cache_dir=cache_dir)

    return _active_provider


def set_active_embedding_provider(provider: EmbeddingProvider) -> None:
    """Override provider (used for test fixtures)."""
    global _active_provider
    _active_provider = provider
