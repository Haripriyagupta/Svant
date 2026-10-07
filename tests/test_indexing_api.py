"""
Tests for Search and Indexing REST API endpoints in SVANT Phase 2.
"""

from __future__ import annotations

from pathlib import Path
import pytest
from starlette.testclient import TestClient

from svant.api.app import create_app
from svant.core.embeddings import MockEmbeddingProvider, set_active_embedding_provider
from svant.db.connection import DatabaseManager, get_db
from svant.db.repository import Repository


@pytest.fixture
def client_env(tmp_path: Path):
    db_file = tmp_path / "api_test.db"
    db_mgr = DatabaseManager(db_file)

    # Set mock provider so API calls don't load external models
    mock_provider = MockEmbeddingProvider(dimension=32)
    set_active_embedding_provider(mock_provider)

    app = create_app()

    # Override repository in route handlers
    from svant.api.routes import projects, files, search, stats, indexing
    test_repo = Repository(db_mgr)
    projects.get_repository = lambda: test_repo
    files.get_repository = lambda: test_repo
    stats.get_repository = lambda: test_repo
    indexing.get_repository = lambda: test_repo
    search.get_search_service = lambda: search.SearchService(test_repo, mock_provider)

    client = TestClient(app)
    return {"client": client, "tmp_path": tmp_path, "repo": test_repo}


def test_api_indexing_and_search_flow(client_env):
    client = client_env["client"]
    tmp_path = client_env["tmp_path"]

    # 1. Create a project folder on disk
    pdir = tmp_path / "project_api"
    pdir.mkdir()
    (pdir / "config.json").write_text('{"app": "SVANT", "version": "0.2.0"}', encoding="utf-8")
    (pdir / "manual.txt").write_text("System user manual describing local vector intelligence.", encoding="utf-8")

    # 2. Register project via API
    res = client.post("/api/projects", json={"path": str(pdir), "name": "APIProject"})
    assert res.status_code == 201
    proj_id = res.json()["id"]

    # 3. Check initial index status -> not_indexed
    res_status = client.get(f"/api/projects/{proj_id}/index/status")
    assert res_status.status_code == 200
    assert res_status.json()["status"] == "not_indexed"

    # 4. Scan project
    res_scan = client.post(f"/api/projects/{proj_id}/scan")
    assert res_scan.status_code == 200
    assert res_scan.json()["total_scanned"] == 2

    # 5. Index project
    res_idx = client.post(f"/api/projects/{proj_id}/index", json={"force_rebuild": False})
    assert res_idx.status_code == 200
    idx_data = res_idx.json()
    assert idx_data["status"] == "success"
    assert idx_data["indexed_files"] == 2
    assert idx_data["total_chunks"] >= 2

    # 6. Check updated index status
    res_status2 = client.get(f"/api/projects/{proj_id}/index/status")
    assert res_status2.status_code == 200
    assert res_status2.json()["status"] == "indexed"
    assert res_status2.json()["total_chunks"] >= 2

    # 7. Search in keyword mode
    res_kw = client.get(f"/api/search?q=manual&project_id={proj_id}&mode=keyword")
    assert res_kw.status_code == 200
    assert res_kw.json()["mode"] == "keyword"
    assert len(res_kw.json()["results"]) > 0

    # 8. Search in semantic mode
    res_sem = client.get(f"/api/search?q=vector+intelligence&project_id={proj_id}&mode=semantic")
    assert res_sem.status_code == 200
    assert res_sem.json()["mode"] == "semantic"
    assert len(res_sem.json()["results"]) > 0

    # 9. Search in hybrid mode
    res_hyb = client.get(f"/api/search?q=SVANT+version&project_id={proj_id}&mode=hybrid")
    assert res_hyb.status_code == 200
    assert res_hyb.json()["mode"] == "hybrid"
    assert len(res_hyb.json()["results"]) > 0
