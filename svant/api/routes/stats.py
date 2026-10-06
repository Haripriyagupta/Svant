"""
Dashboard statistics endpoints.
"""

from fastapi import APIRouter
from svant.api.schemas import DashboardStatsResponse
from svant.db.connection import get_db
from svant.db.repository import Repository

router = APIRouter(prefix="/api/stats", tags=["Stats"])


@router.get("", response_model=DashboardStatsResponse)
def get_stats() -> DashboardStatsResponse:
    """Retrieve aggregate metrics for the dashboard view."""
    repo = Repository(get_db())
    stats = repo.get_dashboard_stats()
    return DashboardStatsResponse(**stats)
