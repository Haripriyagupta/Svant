"""
Pydantic API request and response schemas for SVANT.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    app: str = "SVANT"
    version: str = "0.1.0"
    database: str
    data_dir: str


class ProjectCreateRequest(BaseModel):
    path: str = Field(..., description="Local filesystem path to the project root folder")
    name: Optional[str] = Field(None, description="Optional custom display name for the project")


class ProjectResponse(BaseModel):
    id: str
    name: str
    root_path: str
    status: str
    file_count: int
    total_size_bytes: int
    last_scanned_at: Optional[str] = None
    created_at: str
    updated_at: str


class FileItemResponse(BaseModel):
    id: str
    project_id: str
    project_name: Optional[str] = None
    path: str
    relative_path: str
    filename: str
    extension: str
    category: str
    mime_type: Optional[str] = None
    size_bytes: int
    modified_time: str
    created_time: Optional[str] = None
    sha256: Optional[str] = None
    scan_status: str
    indexed_status: str


class FileDetailResponse(FileItemResponse):
    content_preview: Optional[str] = None
    char_count: Optional[int] = 0
    extraction_status: Optional[str] = None
    extraction_error: Optional[str] = None


class SearchHit(BaseModel):
    file_id: str
    project_id: str
    project_name: str
    filename: str
    relative_path: str
    snippet: str
    score: float
    category: str
    size_bytes: int
    modified_time: str


class SearchResponse(BaseModel):
    query: str
    total: int
    mode: str = "keyword"
    results: List[SearchHit]


class DashboardStatsResponse(BaseModel):
    total_projects: int
    total_files: int
    total_size_bytes: int
    total_indexed_files: int
    last_scanned_at: Optional[str] = None
    categories: Dict[str, Any]
    database_status: str


class ScanResultResponse(BaseModel):
    status: str
    message: str
    project_id: str
    total_scanned: int
    total_size_bytes: int
    indexed_count: int
    duration_seconds: float
