"""
Search engine service for SVANT.
Implements:
1. Keyword search (SQLite FTS5 BM25)
2. Semantic search (FAISS cosine similarity via unit-normalized embeddings)
3. Hybrid search (Score-normalized weighted combination of FTS5 + FAISS)
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from svant.config import settings
from svant.core.embeddings import EmbeddingProvider, get_embedding_provider
from svant.core.vector_store import FAISSVectorStore, get_project_index_path
from svant.db.repository import Repository
from svant.logger import get_logger

logger = get_logger("svant.core.search")


class SearchMode(str, Enum):
    KEYWORD = "keyword"
    SEMANTIC = "semantic"
    HYBRID = "hybrid"


class SearchResultItem:
    """Formatted search hit item."""

    def __init__(
        self,
        file_id: str,
        project_id: str,
        project_name: str,
        filename: str,
        relative_path: str,
        snippet: str,
        score: float,
        category: str,
        size_bytes: int,
        modified_time: str,
        chunk_id: Optional[str] = None,
        match_mode: str = "keyword",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.file_id = file_id
        self.project_id = project_id
        self.project_name = project_name
        self.filename = filename
        self.relative_path = relative_path
        self.snippet = snippet
        self.score = score
        self.category = category
        self.size_bytes = size_bytes
        self.modified_time = modified_time
        self.chunk_id = chunk_id
        self.match_mode = match_mode
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_id": self.file_id,
            "project_id": self.project_id,
            "project_name": self.project_name,
            "filename": self.filename,
            "relative_path": self.relative_path,
            "snippet": self.snippet,
            "score": round(self.score, 4),
            "category": self.category,
            "size_bytes": self.size_bytes,
            "modified_time": self.modified_time,
            "chunk_id": self.chunk_id,
            "match_mode": self.match_mode,
            "metadata": self.metadata,
        }


class SearchService:
    """Unified Search Service handling Keyword, Semantic, and Hybrid queries."""

    def __init__(
        self,
        repo: Repository,
        embedding_provider: Optional[EmbeddingProvider] = None,
    ) -> None:
        self.repo = repo
        self.embedding_provider = embedding_provider or get_embedding_provider()

    def search(
        self,
        query: str,
        project_id: Optional[str] = None,
        mode: SearchMode = SearchMode.KEYWORD,
        limit: int = 25,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Execute search across indexed project files.
        """
        clean_query = query.strip()
        if not clean_query:
            return []

        if mode == SearchMode.KEYWORD:
            return self._search_keyword(clean_query, project_id=project_id, limit=limit, offset=offset)
        elif mode == SearchMode.SEMANTIC:
            return self._search_semantic(clean_query, project_id=project_id, limit=limit, offset=offset)
        elif mode == SearchMode.HYBRID:
            return self._search_hybrid(clean_query, project_id=project_id, limit=limit, offset=offset)
        else:
            raise ValueError(f"Unsupported search mode: {mode}")

    # -------------------------------------------------------------------------
    # 1. KEYWORD SEARCH (SQLite FTS5 BM25)
    # -------------------------------------------------------------------------
    def _search_keyword(
        self,
        query: str,
        project_id: Optional[str] = None,
        limit: int = 25,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Perform SQLite FTS5 keyword search."""
        raw_results = self.repo.search_fts(query=query, project_id=project_id, limit=limit, offset=offset)
        results: List[Dict[str, Any]] = []

        for row in raw_results:
            snippet_text = row.get("snippet", "")
            if not snippet_text:
                snippet_text = f"Found in {row.get('filename')}"

            item = SearchResultItem(
                file_id=row["file_id"],
                project_id=row["project_id"],
                project_name=row.get("project_name", "Unknown"),
                filename=row["filename"],
                relative_path=row["relative_path"],
                snippet=snippet_text,
                score=float(row.get("rank", 0.0)),
                category=row.get("category", "other"),
                size_bytes=int(row.get("size_bytes", 0)),
                modified_time=str(row.get("modified_time", "")),
                match_mode="keyword",
            )
            results.append(item.to_dict())

        return results

    # -------------------------------------------------------------------------
    # 2. SEMANTIC SEARCH (FAISS Inner Product / Cosine Similarity)
    # -------------------------------------------------------------------------
    def _search_semantic(
        self,
        query: str,
        project_id: Optional[str] = None,
        limit: int = 25,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Embed query, perform FAISS vector similarity search, and map back to SQLite chunks.
        """
        # 1. Embed search query
        query_vector = self.embedding_provider.embed_query(query)

        # 2. Determine target projects
        if project_id:
            proj = self.repo.get_project(project_id)
            projects_to_search = [proj] if proj else []
        else:
            projects_to_search = self.repo.list_projects()

        all_hits: List[Dict[str, Any]] = []

        for p in projects_to_search:
            pid = p["id"]
            index_path = get_project_index_path(pid)
            if not index_path.is_file():
                continue

            try:
                store = FAISSVectorStore(
                    dimension=self.embedding_provider.dimension,
                    index_path=index_path,
                )
                if store.count() == 0:
                    continue

                # Query vector store for top candidates
                k = limit + offset
                faiss_results = store.search(query_vector, top_k=k)
                if not faiss_results:
                    continue

                vector_ids = [r.vector_id for r in faiss_results]
                score_by_vid = {r.vector_id: r.score for r in faiss_results}

                # Retrieve chunk details from SQLite
                chunks = self.repo.get_chunks_by_vector_ids(vector_ids)

                for chk in chunks:
                    sim_score = score_by_vid.get(chk["vector_id"], 0.0)
                    all_hits.append({
                        "file_id": chk["file_id"],
                        "project_id": chk["project_id"],
                        "project_name": chk.get("project_name", p.get("name", "Unknown")),
                        "filename": chk["filename"],
                        "relative_path": chk["relative_path"],
                        "snippet": chk["text"],
                        "score": float(sim_score),
                        "category": chk.get("category", "document"),
                        "size_bytes": int(chk.get("size_bytes", 0)),
                        "modified_time": str(chk.get("modified_time", "")),
                        "chunk_id": chk["chunk_id"],
                        "match_mode": "semantic",
                        "metadata": chk.get("metadata", {}),
                    })

            except Exception as e:
                logger.warning(f"Error querying FAISS index for project {pid}: {e}")

        # Sort all candidates by descending similarity score
        all_hits.sort(key=lambda x: x["score"], reverse=True)

        # Paginate
        paginated = all_hits[offset : offset + limit]

        results = [SearchResultItem(**item).to_dict() for item in paginated]
        return results

    # -------------------------------------------------------------------------
    # 3. HYBRID SEARCH (FTS5 BM25 + FAISS Semantic Normalized Fusion)
    # -------------------------------------------------------------------------
    def _search_hybrid(
        self,
        query: str,
        project_id: Optional[str] = None,
        limit: int = 25,
        offset: int = 0,
        semantic_weight: Optional[float] = None,
        keyword_weight: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Combine BM25 full-text keyword retrieval with FAISS dense vector search.
        Normalizes relevance scores to [0, 1] range and applies weighted linear combination.
        """
        w_sem = semantic_weight if semantic_weight is not None else settings.hybrid_semantic_weight
        w_kw = keyword_weight if keyword_weight is not None else settings.hybrid_keyword_weight

        candidate_pool = max(limit * 3, 50)

        # 1. Gather candidate hits from both subsystems
        kw_hits = self._search_keyword(query, project_id=project_id, limit=candidate_pool, offset=0)
        sem_hits = self._search_semantic(query, project_id=project_id, limit=candidate_pool, offset=0)

        # 2. Normalize keyword BM25 scores (BM25 ranks are <= 0, where lower/more negative is better)
        kw_norm_by_file: Dict[str, float] = {}
        if kw_hits:
            ranks = [h["score"] for h in kw_hits]
            min_r = min(ranks)  # best score
            max_r = max(ranks)  # worst score

            for h in kw_hits:
                fid = h["file_id"]
                if max_r == min_r:
                    norm = 1.0
                else:
                    # Invert rank: most negative gets 1.0, least negative gets 0.3
                    norm = 0.3 + 0.7 * ((max_r - h["score"]) / (max_r - min_r))
                kw_norm_by_file[fid] = norm

        # 3. Normalize semantic scores (cosine similarity typically in [0, 1])
        sem_norm_by_file: Dict[str, float] = {}
        if sem_hits:
            for h in sem_hits:
                fid = h["file_id"]
                # Clamp cosine similarity between 0.0 and 1.0
                clamped = max(0.0, min(1.0, float(h["score"])))
                # If multiple chunks from same file, keep highest
                if fid not in sem_norm_by_file or clamped > sem_norm_by_file[fid]:
                    sem_norm_by_file[fid] = clamped

        # 4. Fusion and de-duplication by file_id
        all_file_ids = set(kw_norm_by_file.keys()) | set(sem_norm_by_file.keys())
        kw_map = {h["file_id"]: h for h in kw_hits}
        sem_map = {h["file_id"]: h for h in sem_hits}

        fused_items: List[Dict[str, Any]] = []

        for fid in all_file_ids:
            s_norm = sem_norm_by_file.get(fid, 0.0)
            k_norm = kw_norm_by_file.get(fid, 0.0)

            # Weighted linear combination
            composite_score = (w_sem * s_norm) + (w_kw * k_norm)

            # Choose best representation and snippet
            if fid in sem_map and fid in kw_map:
                base = sem_map[fid]
                match_label = "hybrid (both)"
                # Prefer semantic passage snippet as it is more contextually complete
                snippet = sem_map[fid]["snippet"]
            elif fid in sem_map:
                base = sem_map[fid]
                match_label = "hybrid (semantic)"
                snippet = sem_map[fid]["snippet"]
            else:
                base = kw_map[fid]
                match_label = "hybrid (keyword)"
                snippet = kw_map[fid]["snippet"]

            fused_items.append({
                "file_id": base["file_id"],
                "project_id": base["project_id"],
                "project_name": base["project_name"],
                "filename": base["filename"],
                "relative_path": base["relative_path"],
                "snippet": snippet,
                "score": float(composite_score),
                "category": base["category"],
                "size_bytes": base["size_bytes"],
                "modified_time": base["modified_time"],
                "chunk_id": base.get("chunk_id"),
                "match_mode": match_label,
                "metadata": {
                    "semantic_score": round(s_norm, 4),
                    "keyword_score": round(k_norm, 4),
                    "weights": {"semantic": w_sem, "keyword": w_kw},
                },
            })

        # Sort descending by composite score
        fused_items.sort(key=lambda x: x["score"], reverse=True)

        paginated = fused_items[offset : offset + limit]
        return [SearchResultItem(**item).to_dict() for item in paginated]
