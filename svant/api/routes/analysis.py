"""
API routes for SVANT Project Intelligence, Health, Security, and AI Insights (Phase 4 & 5).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status

from svant.api.schemas import (
    AIActionResponse,
    CitationItem,
    DuplicateClusterResponse,
    FindingResponse,
    FindingStatusUpdateRequest,
    ProjectHealthResponse,
    ProjectSummaryResponse,
    RecommendationsResponse,
)
from svant.config import settings
from svant.core.ai.factory import get_ai_provider
from svant.core.assistant import ProjectAssistant
from svant.core.intelligence.analyzer import ProjectIntelligenceEngine
from svant.core.privacy.redactor import SecretRedactor
from svant.db.connection import get_db
from svant.db.repository import Repository
from svant.logger import get_logger

logger = get_logger("svant.api.routes.analysis")

router = APIRouter(prefix="/api/projects/{project_id}", tags=["Project Intelligence & Health"])


def get_intelligence_engine() -> ProjectIntelligenceEngine:
    db = get_db()
    repo = Repository(db)
    redactor = SecretRedactor()
    return ProjectIntelligenceEngine(repo=repo, redactor=redactor)


def get_project_assistant() -> ProjectAssistant:
    db = get_db()
    repo = Repository(db)
    redactor = SecretRedactor()
    return ProjectAssistant(repo=repo, redactor=redactor)


@router.post("/analyze")
def run_project_analysis(
    project_id: str,
    engine: ProjectIntelligenceEngine = Depends(get_intelligence_engine),
) -> Dict[str, Any]:
    """
    Trigger full project intelligence, security, and health analysis.
    Executes all analyzers, computes explainable health score, and updates findings.
    """
    repo = Repository(get_db())
    project = repo.get_project(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found.",
        )

    try:
        result = engine.run_analysis(project_id)
        return {
            "status": "success",
            "message": "Project intelligence analysis completed successfully.",
            "project_id": project_id,
            "overall_score": result["health"]["overall_score"],
            "grade": result["health"]["grade"],
            "summary": result["health"]["summary"],
            "findings_count": len(result["findings"]),
            "health": result["health"],
        }
    except RuntimeError as rerr:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(rerr),
        )
    except Exception as exc:
        logger.error(f"Analysis failed for project {project_id}: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Analysis failed: {str(exc)}",
        )


@router.get("/health", response_model=ProjectHealthResponse)
def get_project_health(
    project_id: str,
    engine: ProjectIntelligenceEngine = Depends(get_intelligence_engine),
) -> ProjectHealthResponse:
    """Retrieve the latest health score and component breakdown for a project."""
    repo = Repository(get_db())
    project = repo.get_project(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found.",
        )

    health_data = engine.get_health(project_id)
    if not health_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No health analysis found for this project. Please run analysis first.",
        )

    return ProjectHealthResponse(
        project_id=project_id,
        overall_score=health_data.get("overall_score", 0),
        grade=health_data.get("grade", "N/A"),
        summary=health_data.get("summary", ""),
        critical_count=health_data.get("critical_count", 0),
        high_count=health_data.get("high_count", 0),
        medium_count=health_data.get("medium_count", 0),
        low_count=health_data.get("low_count", 0),
        info_count=health_data.get("info_count", 0),
        component_scores=health_data.get("component_scores", {}),
        analyzed_at=health_data.get("analyzed_at"),
    )


@router.get("/findings", response_model=List[FindingResponse])
def list_project_findings(
    project_id: str,
    category: Optional[str] = Query(None, description="Filter by finding category"),
    severity: Optional[str] = Query(None, description="Filter by severity level"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status (open, acknowledged, resolved, ignored)"),
    priority_tier: Optional[str] = Query(None, description="Filter by priority tier"),
    engine: ProjectIntelligenceEngine = Depends(get_intelligence_engine),
) -> List[FindingResponse]:
    """Retrieve intelligence findings for a project with optional filters."""
    repo = Repository(get_db())
    project = repo.get_project(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found.",
        )

    raw_findings = engine.get_findings(
        project_id=project_id,
        category=category,
        severity=severity,
        status=status_filter,
        priority_tier=priority_tier,
    )
    return [FindingResponse(**f) for f in raw_findings]


@router.patch("/findings/{finding_id}", response_model=FindingResponse)
def update_finding_status(
    project_id: str,
    finding_id: str,
    payload: FindingStatusUpdateRequest,
    engine: ProjectIntelligenceEngine = Depends(get_intelligence_engine),
) -> FindingResponse:
    """Update status of a specific finding (open, acknowledged, resolved, ignored)."""
    repo = Repository(get_db())
    finding = repo.get_finding(finding_id)
    if not finding or finding.get("project_id") != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Finding '{finding_id}' not found in project '{project_id}'.",
        )

    try:
        updated = engine.update_finding_status(finding_id, payload.status)
        if not updated:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Failed to update finding.",
            )
        return FindingResponse(**updated)
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(ve),
        )


@router.get("/recommendations", response_model=RecommendationsResponse)
def get_project_recommendations(
    project_id: str,
    engine: ProjectIntelligenceEngine = Depends(get_intelligence_engine),
) -> RecommendationsResponse:
    """Retrieve actionable recommendations organized by priority tiers."""
    repo = Repository(get_db())
    project = repo.get_project(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found.",
        )

    recs = engine.get_recommendations(project_id)
    return RecommendationsResponse(**recs)


@router.get("/statistics")
def get_project_statistics(
    project_id: str,
    engine: ProjectIntelligenceEngine = Depends(get_intelligence_engine),
) -> Dict[str, Any]:
    """Retrieve project file inventory and composition statistics."""
    repo = Repository(get_db())
    project = repo.get_project(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found.",
        )

    return engine.get_statistics(project_id)


@router.get("/duplicates", response_model=List[DuplicateClusterResponse])
def get_project_duplicates(
    project_id: str,
    engine: ProjectIntelligenceEngine = Depends(get_intelligence_engine),
) -> List[DuplicateClusterResponse]:
    """Identify duplicate file clusters grouped by SHA-256 hash."""
    repo = Repository(get_db())
    project = repo.get_project(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found.",
        )

    clusters = engine.get_duplicates(project_id)
    return [DuplicateClusterResponse(**c) for c in clusters]


# =====================================================================
# PROJECT SUMMARY & AI ASSISTANT ENDPOINTS (Grounded in Health & Evidence)
# =====================================================================

@router.get("/summary", response_model=ProjectSummaryResponse)
def get_project_summary(
    project_id: str,
    assistant: ProjectAssistant = Depends(get_project_assistant),
) -> ProjectSummaryResponse:
    """Retrieve structured overview, metrics, and health data for a project."""
    repo = Repository(get_db())
    project = repo.get_project(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found.",
        )
    data = assistant.get_structured_summary(project_id)
    return ProjectSummaryResponse(**data)


@router.post("/ai/summarize", response_model=AIActionResponse)
def ai_summarize_project(
    project_id: str,
    provider: Optional[str] = Query(None, description="AI provider override"),
    assistant: ProjectAssistant = Depends(get_project_assistant),
) -> AIActionResponse:
    """Generate a comprehensive, grounded executive summary of the project."""
    repo = Repository(get_db())
    project = repo.get_project(project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Project '{project_id}' not found.")

    res = assistant.summarize_project(project_id, provider_name=provider)
    sources = [CitationItem(**s) for s in res.get("sources", [])]
    return AIActionResponse(
        project_id=project_id,
        action="summarize",
        content=res["content"],
        provider=res["provider"],
        sources=sources,
    )


@router.post("/ai/plan", response_model=AIActionResponse)
def ai_create_improvement_plan(
    project_id: str,
    provider: Optional[str] = Query(None, description="AI provider override"),
    assistant: ProjectAssistant = Depends(get_project_assistant),
) -> AIActionResponse:
    """Generate a phased, prioritized step-by-step remediation plan."""
    repo = Repository(get_db())
    project = repo.get_project(project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Project '{project_id}' not found.")

    res = assistant.create_improvement_plan(project_id, provider_name=provider)
    sources = [CitationItem(**s) for s in res.get("sources", [])]
    return AIActionResponse(
        project_id=project_id,
        action="plan",
        content=res["content"],
        provider=res["provider"],
        sources=sources,
    )


@router.post("/ai/explain-finding/{finding_id}", response_model=AIActionResponse)
def ai_explain_finding(
    project_id: str,
    finding_id: str,
    provider: Optional[str] = Query(None, description="AI provider override"),
    assistant: ProjectAssistant = Depends(get_project_assistant),
) -> AIActionResponse:
    """Provide a developer-friendly explanation, impact analysis, and code fix for a specific finding."""
    repo = Repository(get_db())
    finding = repo.get_finding(finding_id)
    if not finding or finding.get("project_id") != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Finding '{finding_id}' not found in project '{project_id}'.",
        )

    res = assistant.explain_finding(project_id, finding_id, provider_name=provider)
    sources = [CitationItem(**s) for s in res.get("sources", [])]
    return AIActionResponse(
        project_id=project_id,
        action="explain_finding",
        content=res["content"],
        provider=res["provider"],
        sources=sources,
    )


@router.post("/ai/onboarding", response_model=AIActionResponse)
def ai_onboard_project(
    project_id: str,
    provider: Optional[str] = Query(None, description="AI provider override"),
    assistant: ProjectAssistant = Depends(get_project_assistant),
) -> AIActionResponse:
    """Generate an onboarding guide for new contributors based on scanned project evidence."""
    repo = Repository(get_db())
    project = repo.get_project(project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Project '{project_id}' not found.")

    res = assistant.create_onboarding_guide(project_id, provider_name=provider)
    sources = [CitationItem(**s) for s in res.get("sources", [])]
    return AIActionResponse(
        project_id=project_id,
        action="onboarding",
        content=res["content"],
        provider=res["provider"],
        sources=sources,
    )
