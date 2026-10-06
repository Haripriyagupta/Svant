"""
File inspection endpoints for SVANT.
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, status
from svant.api.schemas import FileDetailResponse, FileItemResponse
from svant.db.connection import get_db
from svant.db.repository import Repository

router = APIRouter(prefix="/api/files", tags=["Files"])


def get_repository() -> Repository:
    return Repository(get_db())


@router.get("", response_model=List[FileItemResponse])
def list_files(
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    category: Optional[str] = Query(None, description="Filter by category (source, document, config, etc.)"),
    extension: Optional[str] = Query(None, description="Filter by file extension (e.g. .py)"),
    search: Optional[str] = Query(None, description="Filter by filename or path substring"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> List[FileItemResponse]:
    """Query scanned files with filters and pagination."""
    repo = get_repository()
    files = repo.list_files(
        project_id=project_id,
        category=category,
        extension=extension,
        search=search,
        limit=limit,
        offset=offset,
    )
    return [FileItemResponse(**f) for f in files]


@router.get("/{file_id}", response_model=FileDetailResponse)
def get_file_detail(file_id: str) -> FileDetailResponse:
    """Retrieve file metadata and extracted text preview."""
    repo = get_repository()
    file_record = repo.get_file(file_id)
    if not file_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File with ID '{file_id}' not found.",
        )

    project = repo.get_project(file_record["project_id"])
    project_name = project["name"] if project else "Unknown"

    extraction = repo.get_extraction(file_id)
    content_preview = None
    char_count = 0
    extraction_status = None
    extraction_error = None

    if extraction:
        content_preview = extraction.get("content_text")
        # Cap text preview in API response to 10,000 characters for responsive UI transfer
        if content_preview and len(content_preview) > 10000:
            content_preview = content_preview[:10000] + "\n\n... [Content truncated for preview]"
        char_count = extraction.get("char_count", 0)
        extraction_status = extraction.get("status")
        extraction_error = extraction.get("error_message")

    return FileDetailResponse(
        **file_record,
        project_name=project_name,
        content_preview=content_preview,
        char_count=char_count,
        extraction_status=extraction_status,
        extraction_error=extraction_error,
    )
