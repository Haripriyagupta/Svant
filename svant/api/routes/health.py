"""
Health and status endpoint.
"""

from fastapi import APIRouter, Depends
from svant.api.schemas import HealthResponse
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
