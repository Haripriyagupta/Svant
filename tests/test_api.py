"""
Integration tests for SVANT FastAPI endpoints.
Uses TestClient with isolated temporary database and filesystem.
"""

from pathlib import Path
import pytest
from starlette.testclient import TestClient

from svant.api.app import create_app
from svant.config import settings
from svant.db.connection import get_db, DatabaseManager


@pytest.fixture
def client(tmp_path: Path):
    # Configure isolated data directory
    test_data_dir = tmp_path / "svant_test_data"
    test_data_dir.mkdir()
    settings.data_dir = test_data_dir
    settings.db_path = test_data_dir / "svant.db"
    settings.log_dir = test_data_dir / "logs"

    # Reset default DB manager
    db_mgr = DatabaseManager(settings.db_path)
    # Monkeypatch singleton
    import svant.db.connection as db_conn
    db_conn._default_manager = db_mgr

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


def test_health_endpoint(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["app"] == "SVANT"
    assert data["database"] == "connected"


def test_root_frontend_serves_index(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    assert "SVANT" in response.text
    assert "Local-First Project & File Intelligence" in response.text



def test_full_project_and_search_workflow(client: TestClient, tmp_path: Path):
    # 1. Create a mock project on disk
    project_dir = tmp_path / "demo_repo"
    project_dir.mkdir()
    (project_dir / "service.py").write_text("def process_payment(amount):\n    return f'Charged ${amount}'", encoding="utf-8")
    (project_dir / "notes.txt").write_text("Security guidelines: Never store raw credit card numbers.", encoding="utf-8")

    # 2. Add project via API
    add_resp = client.post("/api/projects", json={"path": str(project_dir), "name": "Demo Repo"})
    assert add_resp.status_code == 201
    proj_data = add_resp.json()
    proj_id = proj_data["id"]
    assert proj_data["name"] == "Demo Repo"
    assert proj_data["file_count"] == 0

    # 3. List projects
    list_resp = client.get("/api/projects")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    # 4. Trigger Scan
    scan_resp = client.post(f"/api/projects/{proj_id}/scan")
    assert scan_resp.status_code == 200
    scan_data = scan_resp.json()
    assert scan_data["total_scanned"] == 2
    assert scan_data["indexed_count"] == 2

    # 5. List Files
    files_resp = client.get(f"/api/files?project_id={proj_id}")
    assert files_resp.status_code == 200
    files_data = files_resp.json()
    assert len(files_data) == 2
    file_ids = [f["id"] for f in files_data]

    # 6. File Details and text preview
    detail_resp = client.get(f"/api/files/{file_ids[0]}")
    assert detail_resp.status_code == 200
    detail_data = detail_resp.json()
    assert detail_data["content_preview"] is not None

    # 7. Search keyword
    search_resp = client.get("/api/search?q=process_payment")
    assert search_resp.status_code == 200
    search_data = search_resp.json()
    assert search_data["total"] >= 1
    assert "process_payment" in search_data["results"][0]["snippet"]

    # 8. Dashboard stats
    stats_resp = client.get("/api/stats")
    assert stats_resp.status_code == 200
    stats = stats_resp.json()
    assert stats["total_projects"] == 1
    assert stats["total_files"] == 2
    assert stats["database_status"] == "connected"

    # 9. Delete project
    del_resp = client.delete(f"/api/projects/{proj_id}")
    assert del_resp.status_code == 200

    # Verify project deleted from DB
    assert len(client.get("/api/projects").json()) == 0
    # Verify disk files still exist!
    assert project_dir.exists()
    assert (project_dir / "service.py").exists()
