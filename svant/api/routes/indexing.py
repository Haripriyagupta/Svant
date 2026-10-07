"""
Indexing endpoints for SVANT Phase 2 Local Intelligence.
Provides triggers and status monitors for vector embedding and FAISS index generation.
"""

from __future__ import annotations

import threading
from typing import Optional, Set
from fastapi import APIRouter, HTTPException, Query, status

from svant.api.schemas import (
    IndexProjectRequest,
    IndexResultResponse,
    IndexStatusResponse,
)
from svant.core.indexing import IndexingPipeline
from svant.db.connection import get_db
from svant.db.repository import Repository
from svant.logger import get_logger

logger = get_logger("svant.api.indexing")
router = APIRouter(prefix="/api/projects", tags=["Indexing"])

_active_indexing_projects: Set[str] = set()
_indexing_lock = threading.Lock()


def get_repository() -> Repository:
    return Repository(get_db())


@router.post("/{project_id}/index", response_model=IndexResultResponse)
def index_project(
    project_id: str,
    payload: Optional[IndexProjectRequest] = None,
) -> IndexResultResponse:
    """
    Incrementally index extractable files in a project for semantic & hybrid search.
    Skips unchanged files based on content hash.
    """
    repo = get_repository()
    project = repo.get_project(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found.",
        )

    with _indexing_lock:
        if project_id in _active_indexing_projects:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Indexing is already in progress for project '{project['name']}'.",
            )
        _active_indexing_projects.add(project_id)

    force_rebuild = payload.force_rebuild if payload else False
    pipeline = IndexingPipeline(repo=repo)

    try:
        summary = pipeline.index_project(project_id=project_id, force_rebuild=force_rebuild)
        return IndexResultResponse(
            status="success",
            message=(
                f"Indexing complete: {summary.indexed_files} indexed, "
                f"{summary.skipped_files} skipped, {summary.total_chunks} chunks stored."
            ),
            project_id=project_id,
            total_files=summary.total_files,
            indexed_files=summary.indexed_files,
            skipped_files=summary.skipped_files,
            failed_files=summary.failed_files,
            total_chunks=summary.total_chunks,
            total_vectors=summary.total_vectors,
            duration_seconds=round(summary.duration_seconds, 2),
        )
    except Exception as e:
        logger.error(f"Indexing error on project {project_id}: {e}", exc_info=True)
        repo.upsert_project_index_status(
            project_id=project_id,
            status="failed",
            error_message=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Indexing failed: {e}",
        )
    finally:
        with _indexing_lock:
            _active_indexing_projects.discard(project_id)


@router.get("/{project_id}/index/status", response_model=IndexStatusResponse)
def get_index_status(project_id: str) -> IndexStatusResponse:
    """Get current vector index status and statistics for a project."""
    repo = get_repository()
    project = repo.get_project(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found.",
        )

    status_row = repo.get_project_index_status(project_id)
    if not status_row:
        return IndexStatusResponse(
            project_id=project_id,
            status="not_indexed",
            total_chunks=0,
            total_vectors=0,
        )

    return IndexStatusResponse(
        project_id=project_id,
        status=status_row.get("status", "not_indexed"),
        model_name=status_row.get("model_name"),
        dimension=status_row.get("dimension"),
        total_chunks=status_row.get("total_chunks", 0),
        total_vectors=status_row.get("total_vectors", 0),
        last_indexed_at=status_row.get("last_indexed_at"),
        error_message=status_row.get("error_message"),
    )


@router.post("/{project_id}/index/rebuild", response_model=IndexResultResponse)
def rebuild_project_index(project_id: str) -> IndexResultResponse:
    """Force re-extract, re-chunk, and re-embed all files for a project."""
    return index_project(project_id, payload=IndexProjectRequest(force_rebuild=True))
