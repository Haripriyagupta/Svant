"""
Health and status endpoint.
"""

from fastapi import APIRouter
from svant.api.schemas import HealthResponse, SettingsResponse
from svant.config import settings
from svant.db.connection import get_db

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    """Check SVANT system health and database connectivity."""
    db = get_db()
    db_status = "connected"
    try:
        with db.session() as conn:
            conn.execute("SELECT 1")
    except Exception:
        db_status = "disconnected"

    return HealthResponse(
        status="ok",
        app=settings.app_name,
        version=settings.version,
        database=db_status,
        data_dir=str(settings.data_dir),
    )


@router.get("/api/settings", response_model=SettingsResponse)
def get_settings() -> SettingsResponse:
    """Retrieve application configuration and storage paths for the Settings page."""
    has_key = bool(settings.gemini_api_key and settings.gemini_api_key.strip())
    return SettingsResponse(
        version=settings.version,
        data_dir=str(settings.data_dir),
        db_path=str(settings.db_path),
        log_dir=str(settings.log_dir),
        indexes_dir=str(settings.indexes_dir),
        models_dir=str(settings.models_dir),
        excluded_dirs=settings.excluded_dirs,
        local_only_mode=settings.local_only_mode,
        ai_provider=settings.ai_provider,
        gemini_configured=has_key,
        gemini_model=settings.gemini_model,
        embedding_model=settings.embedding_model,
        rag_top_k=settings.rag_top_k,
        hybrid_semantic_weight=settings.hybrid_semantic_weight,
        hybrid_keyword_weight=settings.hybrid_keyword_weight,
    )
