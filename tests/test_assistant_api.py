"""
API tests for AI Project Assistant endpoints and conversational follow-ups (Phase 6 & 7).
"""

from __future__ import annotations

import pytest
from pathlib import Path
from starlette.testclient import TestClient

from svant.api.app import create_app
from svant.config import settings
from svant.db.connection import DatabaseManager
import svant.db.connection as db_conn
from svant.db.repository import Repository


@pytest.fixture
def api_test_env(tmp_path: Path):
    db_file = tmp_path / "api_test.db"
    settings.db_path = db_file
    settings.data_dir = tmp_path

    db_mgr = DatabaseManager(db_file)
    db_conn._default_manager = db_mgr
    repo = Repository(db_mgr)

    proj_dir = tmp_path / "web_app"
    proj_dir.mkdir()
    (proj_dir / "app.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8")
    (proj_dir / "README.md").write_text("# WebApp\nRun with uvicorn app:app\n", encoding="utf-8")

    app = create_app()
    client = TestClient(app)
    # Register project
    res = client.post("/api/projects", json={"path": str(proj_dir), "name": "WebApp"})
    assert res.status_code == 201
    proj_id = res.json()["id"]

    # Scan & Analyze
    client.post(f"/api/projects/{proj_id}/scan")
    client.post(f"/api/projects/{proj_id}/analyze")

    return {"client": client, "project_id": proj_id, "repo": repo}


def test_get_project_summary_endpoint(api_test_env):
    client: TestClient = api_test_env["client"]
    project_id = api_test_env["project_id"]

    resp = client.get(f"/api/projects/{project_id}/summary")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["project_id"] == project_id
    assert data["name"] == "WebApp"
    assert data["total_files"] == 2
    assert "app.py" in data["entry_points"]
    assert "health_score" in data


def test_ai_summarize_endpoint(api_test_env):
    client: TestClient = api_test_env["client"]
    project_id = api_test_env["project_id"]

    resp = client.post(f"/api/projects/{project_id}/ai/summarize")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["action"] == "summarize"
    assert "Executive Project Summary: WebApp" in data["content"]
    assert "sources" in data
    assert len(data["sources"]) > 0


def test_ai_improvement_plan_endpoint(api_test_env):
    client: TestClient = api_test_env["client"]
    project_id = api_test_env["project_id"]

    resp = client.post(f"/api/projects/{project_id}/ai/plan")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["action"] == "plan"
    assert "Phased Remediation Plan" in data["content"]
    assert "Phase 1" in data["content"]


def test_ai_onboarding_endpoint(api_test_env):
    client: TestClient = api_test_env["client"]
    project_id = api_test_env["project_id"]

    resp = client.post(f"/api/projects/{project_id}/ai/onboarding")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["action"] == "onboarding"
    assert "Contributor Onboarding Guide: WebApp" in data["content"]
    assert "app.py" in data["content"]
    assert len(data["sources"]) > 0


def test_ai_explain_finding_endpoints(api_test_env):
    client: TestClient = api_test_env["client"]
    project_id = api_test_env["project_id"]

    findings = client.get(f"/api/projects/{project_id}/findings").json()
    assert len(findings) > 0
    fid = findings[0]["id"]

    resp = client.post(f"/api/projects/{project_id}/ai/explain-finding/{fid}")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["action"] == "explain_finding"
    assert "WHAT Was Detected?" in data["content"]
    assert "HOW TO FIX" in data["content"]
    assert len(data["sources"]) == 1


def test_assistant_endpoints_404_handling(api_test_env):
    client: TestClient = api_test_env["client"]
    project_id = api_test_env["project_id"]

    # Missing project
    assert client.get("/api/projects/non-existent-proj/summary").status_code == 404
    assert client.post("/api/projects/non-existent-proj/ai/summarize").status_code == 404
    assert client.post("/api/projects/non-existent-proj/ai/plan").status_code == 404
    assert client.post("/api/projects/non-existent-proj/ai/onboarding").status_code == 404

    # Missing finding
    assert client.post(f"/api/projects/{project_id}/ai/explain-finding/fake-fid").status_code == 404


def test_chat_follow_up_session(api_test_env):
    client: TestClient = api_test_env["client"]
    project_id = api_test_env["project_id"]

    # Turn 1: Ask broad question
    turn1_resp = client.post(
        "/api/chat",
        json={
            "project_id": project_id,
            "message": "What are the priority issues or findings in this project?",
            "search_mode": "hybrid",
        },
    )
    assert turn1_resp.status_code == 200
    t1_data = turn1_resp.json()
    conv_id = t1_data["conversation_id"]
    assert conv_id is not None

    # Turn 2: Follow-up referencing "the first one"
    turn2_resp = client.post(
        "/api/chat",
        json={
            "project_id": project_id,
            "message": "Explain the first finding and how to resolve it.",
            "search_mode": "hybrid",
            "conversation_id": conv_id,
            "history": [
                {"role": "user", "content": "What are the priority issues or findings in this project?"},
                {"role": "assistant", "content": t1_data["answer"]},
            ],
        },
    )
    assert turn2_resp.status_code == 200
    t2_data = turn2_resp.json()
    assert t2_data["conversation_id"] == conv_id
    assert len(t2_data["sources"]) > 0
