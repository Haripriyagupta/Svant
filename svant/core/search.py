"""
Search engine service for SVANT.
Currently implements high-performance SQLite FTS5 local keyword search with BM25 ranking.
Designed with interfaces to seamlessly introduce semantic and hybrid search in Phase 2.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from svant.db.repository import Repository
from svant.logger import get_logger

logger = get_logger("svant.core.search")


class SearchMode(str, Enum):
    KEYWORD = "keyword"
    SEMANTIC = "semantic"  # Phase 2 placeholder
    HYBRID = "hybrid"      # Phase 2 placeholder


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
        }


class SearchService:
    """Reusable Search Service handling keyword queries and future search modes."""

    def __init__(self, repo: Repository) -> None:
        self.repo = repo

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
        In Phase 1, executes SQLite FTS5 keyword search.
        """
        if mode == SearchMode.KEYWORD:
            return self._search_keyword(query, project_id=project_id, limit=limit, offset=offset)
        elif mode in (SearchMode.SEMANTIC, SearchMode.HYBRID):
            logger.info(f"{mode.value.capitalize()} search requested; falling back to Keyword in Phase 1.")
            return self._search_keyword(query, project_id=project_id, limit=limit, offset=offset)
        else:
            raise ValueError(f"Unsupported search mode: {mode}")

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
            # If snippet is empty, provide a clean fallback preview
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
            )
            results.append(item.to_dict())

        return results
