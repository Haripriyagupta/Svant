"""
API routes for SVANT Project Intelligence, Health, Security, and AI Insights (Phase 4 & 5).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status

from svant.api.schemas import (
    AIActionResponse,
    DuplicateClusterResponse,
    FindingResponse,
    FindingStatusUpdateRequest,
    ProjectHealthResponse,
    RecommendationsResponse,
)
from svant.config import settings
from svant.core.ai.factory import get_ai_provider
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
# AI ASSISTANT ENDPOINTS (Grounded in Health & Project Evidence)
# =====================================================================

@router.post("/ai/summarize", response_model=AIActionResponse)
def ai_summarize_project(
    project_id: str,
    provider: Optional[str] = Query(None, description="AI provider override"),
    engine: ProjectIntelligenceEngine = Depends(get_intelligence_engine),
) -> AIActionResponse:
    """Generate a comprehensive, grounded executive summary of the project."""
    repo = Repository(get_db())
    project = repo.get_project(project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Project '{project_id}' not found.")

    health = engine.get_health(project_id)
    findings = engine.get_findings(project_id, status="open")
    stats_data = engine.get_statistics(project_id)

    # Format structured evidence
    evidence = (
        f"Project: {project['name']} (Path: {project['root_path']})\n"
        f"Total Files: {stats_data.get('total_files', 0)}, Total Size: {stats_data.get('total_size_bytes', 0)} bytes\n"
        f"Languages: {stats_data.get('languages', {})}\n"
        f"Health Score: {health.get('overall_score', 'N/A')}/100 (Grade: {health.get('grade', 'N/A')})\n"
        f"Health Summary: {health.get('summary', 'No analysis yet')}\n"
        f"Open Findings ({len(findings)} total):\n"
    )
    for f in findings[:10]:
        evidence += f"- [{f['severity'].upper()}] {f['title']} in {f.get('relative_path') or 'root'}: {f['description']}\n"

    active_provider = get_ai_provider(provider)
    is_mock = (active_provider and active_provider.name == "mock") or (provider == "mock")
    is_local_only = getattr(settings, "local_only_mode", True) and not is_mock
    if provider in ("mock", "gemini"):
        is_local_only = False

    if is_local_only or not active_provider or not active_provider.is_available:
        summary_text = (
            f"### Executive Project Summary: {project['name']}\n\n"
            f"- **Architecture & Scale**: Tracked {stats_data.get('total_files', 0)} files across "
            f"{len(stats_data.get('languages', {}))} languages ({', '.join(stats_data.get('languages', {}).keys()) or 'None'}).\n"
            f"- **Health Rating**: Overall Grade **{health.get('grade', 'N/A')}** ({health.get('overall_score', 0)}/100).\n"
            f"- **Health Overview**: {health.get('summary', 'Analysis pending.')}\n"
            f"- **Active Risks**: {health.get('critical_count', 0)} critical and {health.get('high_count', 0)} high severity issues identified.\n"
            f"- **Key Focus**: Review Fix First recommendations to resolve outstanding security and dependency issues."
        )
        return AIActionResponse(
            project_id=project_id,
            action="summarize",
            content=summary_text,
            provider="local",
        )

    system_prompt = (
        "You are SVANT, an expert project intelligence AI. Provide a concise, highly structured 4-5 bullet point "
        "executive summary of the project based strictly on the provided evidence."
    )
    user_prompt = f"PROJECT EVIDENCE:\n{evidence}\n\nPlease generate the executive project summary."
    res = active_provider.generate(system_prompt=system_prompt, user_prompt=user_prompt, context=evidence)
    return AIActionResponse(
        project_id=project_id,
        action="summarize",
        content=res.text,
        provider=active_provider.name,
    )


@router.post("/ai/plan", response_model=AIActionResponse)
def ai_create_improvement_plan(
    project_id: str,
    provider: Optional[str] = Query(None, description="AI provider override"),
    engine: ProjectIntelligenceEngine = Depends(get_intelligence_engine),
) -> AIActionResponse:
    """Generate a phased, prioritized step-by-step remediation plan."""
    repo = Repository(get_db())
    project = repo.get_project(project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Project '{project_id}' not found.")

    health = engine.get_health(project_id)
    recs = engine.get_recommendations(project_id)
    tiers = recs.get("recommendations_by_tier", {})

    active_provider = get_ai_provider(provider)
    is_mock = (active_provider and active_provider.name == "mock") or (provider == "mock")
    is_local_only = getattr(settings, "local_only_mode", True) and not is_mock
    if provider in ("mock", "gemini"):
        is_local_only = False

    fix_first = tiers.get("fix_first", [])
    should_fix = tiers.get("should_fix", [])
    nice_to_improve = tiers.get("nice_to_improve", [])

    if is_local_only or not active_provider or not active_provider.is_available:
        plan_lines = [
            f"### Phased Remediation Plan for {project['name']}\n",
            f"**Current Health Score**: {health.get('overall_score', 0)}/100 (Grade {health.get('grade', 'N/A')})\n",
            "#### Phase 1: Immediate Remediation (Fix First)",
        ]
        if fix_first:
            for item in fix_first[:5]:
                plan_lines.append(f"- **{item['title']}** (`{item.get('relative_path') or 'root'}`): {item['recommendation']}")
        else:
            plan_lines.append("- *No urgent blockers found.*")

        plan_lines.append("\n#### Phase 2: Important Enhancements (Should Fix)")
        if should_fix:
            for item in should_fix[:5]:
                plan_lines.append(f"- **{item['title']}** (`{item.get('relative_path') or 'root'}`): {item['recommendation']}")
        else:
            plan_lines.append("- *No moderate issues found.*")

        plan_lines.append("\n#### Phase 3: Hygiene & Polish (Nice to Improve)")
        if nice_to_improve:
            for item in nice_to_improve[:5]:
                plan_lines.append(f"- **{item['title']}**: {item['recommendation']}")
        else:
            plan_lines.append("- *Codebase is clean.*")

        return AIActionResponse(
            project_id=project_id,
            action="plan",
            content="\n".join(plan_lines),
            provider="local",
        )

    evidence = (
        f"Project: {project['name']}\n"
        f"Health Score: {health.get('overall_score', 0)}/100\n"
        f"Fix First Items: {fix_first}\n"
        f"Should Fix Items: {should_fix}\n"
        f"Nice to Improve Items: {nice_to_improve}\n"
    )
    system_prompt = (
        "You are SVANT, an expert software architecture AI. Create a phased, actionable, step-by-step remediation plan "
        "divided into Phase 1 (Immediate/Security), Phase 2 (Quality/Testing), and Phase 3 (Hygiene/Polish)."
    )
    user_prompt = f"PROJECT FINDINGS EVIDENCE:\n{evidence}\n\nPlease generate the phased remediation plan."
    res = active_provider.generate(system_prompt=system_prompt, user_prompt=user_prompt, context=evidence)
    return AIActionResponse(
        project_id=project_id,
        action="plan",
        content=res.text,
        provider=active_provider.name,
    )


@router.post("/ai/explain-finding/{finding_id}", response_model=AIActionResponse)
def ai_explain_finding(
    project_id: str,
    finding_id: str,
    provider: Optional[str] = Query(None, description="AI provider override"),
    engine: ProjectIntelligenceEngine = Depends(get_intelligence_engine),
) -> AIActionResponse:
    """Provide a developer-friendly explanation, impact analysis, and code fix for a specific finding."""
    repo = Repository(get_db())
    finding = repo.get_finding(finding_id)
    if not finding or finding.get("project_id") != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Finding '{finding_id}' not found in project '{project_id}'.",
        )

    active_provider = get_ai_provider(provider)
    is_mock = (active_provider and active_provider.name == "mock") or (provider == "mock")
    is_local_only = getattr(settings, "local_only_mode", True) and not is_mock
    if provider in ("mock", "gemini"):
        is_local_only = False

    if is_local_only or not active_provider or not active_provider.is_available:
        explanation = (
            f"### Analysis: {finding['title']}\n\n"
            f"- **Category**: `{finding['category'].title()}` | **Severity**: `{finding['severity'].upper()}`\n"
            f"- **Location**: `{finding.get('relative_path') or 'root'}` ({finding.get('location') or 'file'})\n\n"
            f"#### Issue Description\n"
            f"{finding['description']}\n\n"
            f"#### Evidence Detected\n"
            f"```\n{finding.get('evidence') or 'N/A'}\n```\n\n"
            f"#### Recommended Fix\n"
            f"{finding['recommendation']}\n\n"
            f"#### Why This Matters\n"
            f"Addressing this item enhances overall project health, maintains safety standards, and prevents accumulated technical debt."
        )
        return AIActionResponse(
            project_id=project_id,
            action="explain_finding",
            content=explanation,
            provider="local",
        )

    evidence = (
        f"Finding: {finding['title']}\n"
        f"Category: {finding['category']}\n"
        f"Severity: {finding['severity']}\n"
        f"File: {finding.get('relative_path')}\n"
        f"Location: {finding.get('location')}\n"
        f"Evidence: {finding.get('evidence')}\n"
        f"Description: {finding['description']}\n"
        f"Recommendation: {finding['recommendation']}\n"
    )
    system_prompt = (
        "You are SVANT, an expert software developer and security engineer. Explain this finding clearly to the developer: "
        "detail what happened, why it is dangerous or suboptimal, the potential impact, and give concrete code or config fix instructions."
    )
    user_prompt = f"FINDING EVIDENCE:\n{evidence}\n\nPlease explain this finding and provide remediation steps."
    res = active_provider.generate(system_prompt=system_prompt, user_prompt=user_prompt, context=evidence)
    return AIActionResponse(
        project_id=project_id,
        action="explain_finding",
        content=res.text,
        provider=active_provider.name,
    )
