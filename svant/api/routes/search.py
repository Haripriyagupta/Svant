"""
Search endpoints for SVANT.
"""

from typing import Optional
from fastapi import APIRouter, Query
from svant.api.schemas import SearchHit, SearchResponse
from svant.core.search import SearchMode, SearchService
from svant.db.connection import get_db
from svant.db.repository import Repository

router = APIRouter(prefix="/api/search", tags=["Search"])


def get_search_service() -> SearchService:
    return SearchService(Repository(get_db()))


@router.get("", response_model=SearchResponse)
def search_files(
    q: str = Query(..., min_length=1, description="Search term or natural language query"),
    project_id: Optional[str] = Query(None, description="Optional project filter"),
    mode: str = Query("keyword", description="Search mode: keyword, semantic, hybrid"),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> SearchResponse:
    """Execute keyword (FTS5), semantic (FAISS), or hybrid search across indexed files."""
    service = get_search_service()
    clean_mode = mode.lower().strip()
    if clean_mode == "semantic":
        search_mode = SearchMode.SEMANTIC
    elif clean_mode == "hybrid":
        search_mode = SearchMode.HYBRID
    else:
        search_mode = SearchMode.KEYWORD

    results = service.search(
        query=q,
        project_id=project_id,
        mode=search_mode,
        limit=limit,
        offset=offset,
    )

    return SearchResponse(
        query=q,
        total=len(results),
        mode=search_mode.value,
        results=[SearchHit(**item) for item in results],
    )
