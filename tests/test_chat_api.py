"""
Integration tests for SVANT Grounded AI Chat API (Phase 3).
Tests GET /api/chat/status and POST /api/chat with MockAIProvider.
"""

from pathlib import Path
import pytest
from starlette.testclient import TestClient

from svant.api.app import create_app
from svant.config import settings
from svant.db.connection import DatabaseManager
from svant.core.ai.factory import set_active_ai_provider
from svant.core.ai.mock import MockAIProvider


@pytest.fixture
def client(tmp_path: Path):
    test_data_dir = tmp_path / "svant_chat_test_data"
    test_data_dir.mkdir()
    orig_data_dir = settings.data_dir
    orig_db_path = settings.db_path
    orig_log_dir = settings.log_dir
    orig_models_dir = settings.models_dir
    orig_ai_provider = settings.ai_provider

    settings.data_dir = test_data_dir
    settings.db_path = test_data_dir / "svant.db"
    settings.log_dir = test_data_dir / "logs"
    settings.models_dir = test_data_dir / "models"
    settings.ai_provider = "mock"

    # Set mock provider for tests
    set_active_ai_provider(MockAIProvider())

    db_mgr = DatabaseManager(settings.db_path)
    import svant.db.connection as db_conn
    db_conn._default_manager = db_mgr

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client

    # Teardown
    set_active_ai_provider(None)
    settings.data_dir = orig_data_dir
    settings.db_path = orig_db_path
    settings.log_dir = orig_log_dir
    settings.models_dir = orig_models_dir
    settings.ai_provider = orig_ai_provider


def test_chat_status_endpoint(client: TestClient):
    response = client.get("/api/chat/status")
    assert response.status_code == 200
    data = response.json()
    assert data["active_provider"] == "mock"
    assert data["is_available"] is True
    assert "gemini_model" in data


def test_full_rag_chat_workflow(client: TestClient, tmp_path: Path):
    # 1. Create a mock codebase with domain content
    project_dir = tmp_path / "telemetry_service"
    project_dir.mkdir()

    config_content = (
        "# Configuration Module\n"
        "TELEMETRY_PORT = 9100\n"
        "METRICS_PATH = '/metrics'\n"
        "BATCH_SIZE = 500\n"
    )
    (project_dir / "config.py").write_text(config_content, encoding="utf-8")

    readme_content = (
        "# Telemetry Microservice\n"
        "Collects system performance metrics across nodes.\n"
        "Exports Prometheus metrics on port 9100.\n"
    )
    (project_dir / "README.md").write_text(readme_content, encoding="utf-8")

    # 2. Add project
    add_resp = client.post("/api/projects", json={"path": str(project_dir), "name": "Telemetry"})
    assert add_resp.status_code == 201
    proj_id = add_resp.json()["id"]

    # 3. Scan project
    scan_resp = client.post(f"/api/projects/{proj_id}/scan")
    assert scan_resp.status_code == 200

    # 4. Index project (Chunking + FAISS embeddings)
    idx_resp = client.post(f"/api/projects/{proj_id}/index")
    assert idx_resp.status_code == 200
    assert idx_resp.json()["total_chunks"] >= 2

    # 5. Send RAG Chat Query
    chat_payload = {
        "message": "What port does the telemetry service export metrics on?",
        "project_id": proj_id,
        "search_mode": "hybrid",
        "top_k": 5,
    }
    chat_resp = client.post("/api/chat", json=chat_payload)
    assert chat_resp.status_code == 200
    data = chat_resp.json()

    assert data["provider"] == "mock"
    assert len(data["sources"]) >= 1
    # Check citation filenames
    citation_files = [c["filename"] for c in data["sources"]]
    assert "README.md" in citation_files or "config.py" in citation_files
    # Check answer text
    assert len(data["answer"]) > 0


def test_chat_with_secret_redaction(client: TestClient, tmp_path: Path):
    # Create project with a file containing an API key
    project_dir = tmp_path / "secret_repo"
    project_dir.mkdir()

    fake_gh_token = "gh" + "p_" + "123456789012345678901234567890123456"
    env_content = (
        "APP_NAME=AuthApp\n"
        f"GITHUB_ACCESS_TOKEN={fake_gh_token}\n"
        "DEBUG=False\n"
    )
    (project_dir / "auth.py").write_text(env_content, encoding="utf-8")

    add_resp = client.post("/api/projects", json={"path": str(project_dir), "name": "SecretRepo"})
    proj_id = add_resp.json()["id"]

    client.post(f"/api/projects/{proj_id}/scan")
    client.post(f"/api/projects/{proj_id}/index")

    # Ask chat about the auth tokens using hybrid search
    chat_payload = {
        "message": "What is the GITHUB_ACCESS_TOKEN configured in auth.py?",
        "project_id": proj_id,
        "search_mode": "hybrid",
    }
    chat_resp = client.post("/api/chat", json=chat_payload)
    assert chat_resp.status_code == 200
    data = chat_resp.json()

    # Redactions must have occurred locally
    assert data["redactions"] >= 1
    # Raw token must not appear in answer or citations
    assert fake_gh_token not in data["answer"]
    for c in data["sources"]:
        assert fake_gh_token not in c["snippet_preview"]

    # Also verify that secrets typed in the user's prompt are scrubbed
    user_test_token = "gh" + "p_" + "999999999999999999999999999999999999"
    user_secret_payload = {
        "message": f"Check if token {user_test_token} is present",
        "project_id": proj_id,
        "search_mode": "hybrid",
    }
    user_secret_resp = client.post("/api/chat", json=user_secret_payload)
    assert user_secret_resp.status_code == 200
    user_data = user_secret_resp.json()
    assert user_data["redactions"] >= 1
    assert user_test_token not in user_data["answer"]


def test_chat_nonexistent_project_returns_404(client: TestClient):
    chat_payload = {
        "message": "Where is the main entry point?",
        "project_id": "non-existent-id-12345",
    }
    resp = client.post("/api/chat", json=chat_payload)
    assert resp.status_code == 404


def test_scan_to_index_to_ai_chat_flow(client: TestClient, tmp_path: Path):
    """
    Explicit verification of the complete Scan -> Index -> AI Chat lifecycle:
    1. Scan: Files > 0, Vectors == 0, Status == 'not_indexed'
    2. Index: Files > 0, Vectors > 0, Status == 'indexed'
    3. AI Chat: Context chunks retrieved (len(sources) > 0)
    """
    project_dir = tmp_path / "lifecycle_proj"
    project_dir.mkdir()
    (project_dir / "service.py").write_text(
        "class AuthService:\n    def authenticate(self, username, token):\n        return True\n",
        encoding="utf-8",
    )
    (project_dir / "README.md").write_text(
        "# Authentication Service\nHandles user login and session validation with OAuth tokens.\n",
        encoding="utf-8",
    )

    # Register project
    add_resp = client.post("/api/projects", json={"path": str(project_dir), "name": "AuthService"})
    assert add_resp.status_code == 201
    proj_id = add_resp.json()["id"]

    # Step 1: Scan project
    scan_resp = client.post(f"/api/projects/{proj_id}/scan")
    assert scan_resp.status_code == 200
    assert scan_resp.json()["total_scanned"] == 2

    # Check status before indexing: Files > 0, Vectors == 0, Status == 'not_indexed'
    status_before = client.get(f"/api/projects/{proj_id}/index/status").json()
    proj_before = client.get(f"/api/projects/{proj_id}").json()
    assert proj_before["file_count"] == 2
    assert status_before["total_vectors"] == 0
    assert status_before["status"] == "not_indexed"

    # Step 2: Trigger Indexing
    index_resp = client.post(f"/api/projects/{proj_id}/index")
    assert index_resp.status_code == 200
    assert index_resp.json()["indexed_files"] == 2
    assert index_resp.json()["total_vectors"] > 0

    # Check status after indexing: Files > 0, Vectors > 0, Status == 'indexed'
    status_after = client.get(f"/api/projects/{proj_id}/index/status").json()
    assert status_after["status"] == "indexed"
    assert status_after["total_vectors"] > 0
    assert status_after["total_chunks"] == status_after["total_vectors"]

    # Step 3: Verify AI Chat retrieves context chunks
    chat_resp = client.post(
        "/api/chat",
        json={
            "message": "How does the AuthService validate sessions?",
            "project_id": proj_id,
            "search_mode": "hybrid",
            "top_k": 5,
        },
    )
    assert chat_resp.status_code == 200
    chat_data = chat_resp.json()
    assert len(chat_data["sources"]) > 0, "AI Chat must retrieve context chunks!"
    assert any("AuthService" in s["snippet_preview"] or "Authentication" in s["snippet_preview"] for s in chat_data["sources"])


def test_chat_without_project_id_falls_back_to_first_project(client: TestClient, tmp_path: Path):
    """Verify that when project_id is omitted or empty, chat automatically targets the first active project."""
    project_dir = tmp_path / "fallback_proj"
    project_dir.mkdir()
    (project_dir / "index.js").write_text("console.log('Server started on port 3000');", encoding="utf-8")

    add_resp = client.post("/api/projects", json={"path": str(project_dir), "name": "FallbackProj"})
    assert add_resp.status_code == 201

    client.post(f"/api/projects/{add_resp.json()['id']}/scan")
    client.post(f"/api/projects/{add_resp.json()['id']}/index")

    # 1. Omitted project_id
    resp_omitted = client.post("/api/chat", json={"message": "What port is mentioned in the code?"})
    assert resp_omitted.status_code == 200
    assert "answer" in resp_omitted.json()

    # 2. Empty string project_id
    resp_empty = client.post("/api/chat", json={"message": "What port is mentioned?", "project_id": ""})
    assert resp_empty.status_code == 200
    assert "answer" in resp_empty.json()
