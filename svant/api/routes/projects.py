"""
Projects management endpoints for SVANT.
"""

from pathlib import Path
from typing import List
from fastapi import APIRouter, HTTPException, status
from svant.api.schemas import ProjectCreateRequest, ProjectResponse, ScanResultResponse
from svant.core.scanner import FileScanner
from svant.db.connection import get_db
from svant.db.repository import Repository
from svant.logger import get_logger

logger = get_logger("svant.api.projects")
router = APIRouter(prefix="/api/projects", tags=["Projects"])


def get_repository() -> Repository:
    return Repository(get_db())


@router.get("", response_model=List[ProjectResponse])
def list_projects() -> List[ProjectResponse]:
    """List all tracked projects."""
    repo = get_repository()
    projects = repo.list_projects()
    return [ProjectResponse(**p) for p in projects]


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreateRequest) -> ProjectResponse:
    """Register a local folder as a tracked project."""
    repo = get_repository()
    raw_path = payload.path.strip()

    if not raw_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project folder path cannot be empty.",
        )

    # Resolve and validate directory
    try:
        resolved_path = Path(raw_path).resolve()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid path format: {e}",
        )

    if not resolved_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Directory '{resolved_path}' does not exist on disk.",
        )

    if not resolved_path.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Path '{resolved_path}' is a file, not a directory.",
        )

    # Check for existing project with same path
    canonical_str = str(resolved_path)
    existing = repo.get_project_by_path(canonical_str)
    if existing:
        return ProjectResponse(**existing)

    name = payload.name.strip() if payload.name and payload.name.strip() else resolved_path.name
    if not name:
        name = "Project"

    project = repo.create_project(name=name, root_path=canonical_str)
    logger.info(f"Registered new tracked project: '{name}' -> '{canonical_str}'")
    return ProjectResponse(**project)


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str) -> ProjectResponse:
    """Retrieve details for a specific project."""
    repo = get_repository()
    project = repo.get_project(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found.",
        )
    return ProjectResponse(**project)


@router.post("/{project_id}/scan", response_model=ScanResultResponse)
def scan_project(project_id: str) -> ScanResultResponse:
    """Trigger recursive scan, extraction, and FTS5 indexing on a project."""
    repo = get_repository()
    project = repo.get_project(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found.",
        )

    scanner = FileScanner(repo=repo)
    try:
        summary = scanner.scan_project(project_id=project_id, extract_text=True)
        return ScanResultResponse(
            status="success",
            message=f"Scanned {summary.total_scanned} files successfully.",
            project_id=project_id,
            total_scanned=summary.total_scanned,
            total_size_bytes=summary.total_size_bytes,
            indexed_count=summary.indexed_count,
            duration_seconds=round(summary.duration_seconds, 2),
        )
    except Exception as e:
        logger.error(f"Scan failed for project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Scan failed: {e}",
        )


@router.delete("/{project_id}", status_code=status.HTTP_200_OK)
def delete_project(project_id: str) -> dict:
    """
    Remove a project from SVANT database.
    NEVER deletes or modifies real files on disk.
    """
    repo = get_repository()
    project = repo.get_project(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found.",
        )

    success = repo.delete_project(project_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to remove project from database.",
        )

    logger.info(f"Removed project '{project['name']}' from SVANT tracking (disk untouched).")
    return {"status": "success", "message": f"Project '{project['name']}' untracked successfully."}
