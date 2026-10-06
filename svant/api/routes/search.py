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
    q: str = Query(..., min_length=1, description="Keyword search term"),
    project_id: Optional[str] = Query(None, description="Optional project filter"),
    mode: str = Query("keyword", description="Search mode: keyword (Phase 1), semantic (Phase 2), hybrid (Phase 2)"),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> SearchResponse:
    """Execute keyword full-text search against indexed files."""
    service = get_search_service()
    search_mode = SearchMode.KEYWORD
    if mode.lower() in ("semantic", "hybrid"):
        search_mode = SearchMode(mode.lower())

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
        mode="keyword" if search_mode == SearchMode.KEYWORD else f"{search_mode.value} (fallback keyword in Phase 1)",
        results=[SearchHit(**item) for item in results],
    )
