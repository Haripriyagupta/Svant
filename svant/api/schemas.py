"""
Pydantic API request and response schemas for SVANT.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    app: str = "SVANT"
    version: str = "0.2.0"
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
    chunk_id: Optional[str] = None
    match_mode: str = "keyword"
    metadata: Optional[Dict[str, Any]] = None


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
    total_chunks: int = 0
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


class IndexProjectRequest(BaseModel):
    force_rebuild: bool = False


class IndexResultResponse(BaseModel):
    status: str
    message: str
    project_id: str
    total_files: int
    indexed_files: int
    skipped_files: int
    failed_files: int
    total_chunks: int
    total_vectors: int
    duration_seconds: float


class IndexStatusResponse(BaseModel):
    project_id: str
    status: str
    model_name: Optional[str] = None
    dimension: Optional[int] = None
    total_chunks: int = 0
    total_vectors: int = 0
    last_indexed_at: Optional[str] = None
    error_message: Optional[str] = None


class CitationItem(BaseModel):
    file_id: str
    filename: str
    relative_path: str
    location: str
    relevance_score: float
    snippet_preview: str
    chunk_id: Optional[str] = None


class ChatRequest(BaseModel):
    project_id: str = Field(..., description="Project ID to query")
    message: str = Field(..., min_length=1, description="User question or prompt")
    search_mode: str = Field("hybrid", description="Retrieval mode: hybrid, semantic, keyword")
    top_k: Optional[int] = Field(None, ge=1, le=25, description="Number of context items to retrieve")
    provider: Optional[str] = Field(None, description="Optional provider override: local, gemini, mock")


class ChatResponse(BaseModel):
    answer: str
    provider: str
    mode: str
    sources: List[CitationItem]
    context_count: int
    redactions: int


class AIStatusResponse(BaseModel):
    local_only_mode: bool
    active_provider: str
    gemini_configured: bool
    gemini_model: str
    is_available: bool = True


class FindingResponse(BaseModel):
    id: str
    project_id: str
    category: str
    severity: str
    priority_tier: str = "should_fix"
    title: str
    description: str
    recommendation: str
    file_id: Optional[str] = None
    relative_path: Optional[str] = None
    location: Optional[str] = None
    evidence: Optional[str] = None
    confidence: float = 1.0
    status: str = "open"
    created_at: str = ""
    updated_at: str = ""


class FindingStatusUpdateRequest(BaseModel):
    status: str = Field(..., description="Target status: open, acknowledged, resolved, or ignored")


class ProjectHealthResponse(BaseModel):
    project_id: str
    overall_score: int
    grade: str
    summary: str
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    info_count: int = 0
    component_scores: Dict[str, Any]
    analyzed_at: Optional[str] = None


class RecommendationsResponse(BaseModel):
    project_id: str
    overall_score: Optional[int] = None
    grade: Optional[str] = None
    summary: Optional[str] = None
    total_open: int = 0
    recommendations_by_tier: Dict[str, List[Dict[str, Any]]]


class DuplicateClusterResponse(BaseModel):
    sha256: str
    size_bytes: int
    count: int
    wasted_bytes: int
    files: List[Dict[str, Any]]


class AIActionResponse(BaseModel):
    project_id: str
    action: str
    content: str
    provider: str


