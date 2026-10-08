"""
Grounded AI Chat endpoints for SVANT Phase 3 RAG.
Provides privacy-aware contextual project Q&A with source citations.
"""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException, status

from svant.api.schemas import AIStatusResponse, ChatRequest, ChatResponse, CitationItem
from svant.config import settings
from svant.core.ai.factory import get_ai_provider
from svant.core.rag.pipeline import RAGPipeline
from svant.core.search import SearchMode, SearchService
from svant.db.connection import get_db
from svant.db.repository import Repository
from svant.logger import get_logger

logger = get_logger("svant.api.chat")
router = APIRouter(prefix="/api/chat", tags=["AI Chat"])


def get_rag_pipeline(provider_name: Optional[str] = None) -> RAGPipeline:
    repo = Repository(get_db())
    search_service = SearchService(repo)
    provider = get_ai_provider(provider_name)
    return RAGPipeline(repo=repo, search_service=search_service, ai_provider=provider)


@router.post("", response_model=ChatResponse)
def chat_with_project(payload: ChatRequest) -> ChatResponse:
    """
    Ask a question grounded in a tracked project's files, code, and documentation.
    Retrieves evidence locally, redacts secrets locally, and generates answers with citations.
    """
    repo = Repository(get_db())
    target_project_id = (payload.project_id or "").strip()
    if not target_project_id:
        projects = repo.list_projects()
        if not projects:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No projects found. Please add and scan a project first before asking SVANT.",
            )
        target_project_id = projects[0]["id"]

    project = repo.get_project(target_project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{target_project_id}' not found.",
        )

    mode_str = payload.search_mode.lower().strip()
    if mode_str == "semantic":
        search_mode = SearchMode.SEMANTIC
    elif mode_str == "keyword":
        search_mode = SearchMode.KEYWORD
    else:
        search_mode = SearchMode.HYBRID

    pipeline = get_rag_pipeline(payload.provider)

    try:
        rag_res = pipeline.query(
            project_id=target_project_id,
            message=payload.message,
            search_mode=search_mode,
            top_k=payload.top_k,
            provider_name=payload.provider,
            conversation_id=payload.conversation_id,
            history=payload.history,
        )

        return ChatResponse(
            answer=rag_res.answer,
            provider=rag_res.provider,
            mode=rag_res.mode,
            sources=[CitationItem(**s.to_dict()) for s in rag_res.sources],
            context_count=rag_res.context_count,
            redactions=rag_res.redactions,
            conversation_id=rag_res.conversation_id,
        )

    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(val_err),
        )
    except Exception as exc:
        logger.error(f"Error handling chat request: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred during AI processing: {exc}",
        )


@router.get("/status", response_model=AIStatusResponse)
def get_ai_status() -> AIStatusResponse:
    """Retrieve current AI configuration and privacy mode status (without exposing secrets)."""
    has_key = bool(settings.gemini_api_key and settings.gemini_api_key.strip())
    active_prov = get_ai_provider()
    provider_name = active_prov.name if active_prov else ("local" if settings.local_only_mode else "none")
    is_avail = active_prov.is_available if active_prov else True

    return AIStatusResponse(
        local_only_mode=settings.local_only_mode,
        active_provider=provider_name,
        gemini_configured=has_key,
        gemini_model=settings.gemini_model,
        is_available=is_avail,
    )

