"""
Integration tests for SVANT Project Intelligence & Health REST API (Phase 4 & 5).
Validates analyze endpoint, health, findings filtering, status updates,
recommendations tiers, duplicates, AI summaries/plans/explanations, and RAG grounding.
"""

from __future__ import annotations

import os
from pathlib import Path
import pytest
from starlette.testclient import TestClient

from svant.api.app import create_app
from svant.config import settings
from svant.core.classifier import FileClassifier
from svant.core.extractor import DocumentExtractor
from svant.core.scanner import FileScanner
from svant.db.connection import DatabaseManager
from svant.db.repository import Repository


@pytest.fixture
def test_env(tmp_path: Path):
    """Sets up an isolated test data directory, database, and client."""
    data_dir = tmp_path / "svant_data"
    data_dir.mkdir()
    db_file = data_dir / "svant.db"

    # Set environment variables
    old_data_dir = os.environ.get("SVANT_DATA_DIR")
    old_local_only = os.environ.get("SVANT_LOCAL_ONLY_MODE")
    os.environ["SVANT_DATA_DIR"] = str(data_dir)
    os.environ["SVANT_LOCAL_ONLY_MODE"] = "true"

    settings.data_dir = data_dir
    settings.db_path = db_file
    settings.local_only_mode = True

    db_mgr = DatabaseManager(db_file)
    import svant.db.connection as db_conn
    db_conn._default_manager = db_mgr

    repo = Repository(db_mgr)

    # Create realistic test project
    proj_dir = tmp_path / "target_project"
    proj_dir.mkdir()

    # Create files
    src = proj_dir / "src"
    src.mkdir()
    (src / "app.py").write_text("print('hello')\n# TODO: optimize\n", encoding="utf-8")
    (src / "insecure.py").write_text("import requests\nDEBUG = True\nrequests.get('https://example.com', verify=False)\n", encoding="utf-8")
    (proj_dir / "README.md").write_text("# Target Project\nShort readme", encoding="utf-8")
    (proj_dir / "requirements.txt").write_text("fastapi\nrequests==2.31.0\n", encoding="utf-8")

    # Clutter & duplicates
    (src / "dup1.txt").write_text("Duplicate file content here.", encoding="utf-8")
    (src / "dup2.txt").write_text("Duplicate file content here.", encoding="utf-8")

    # Synthetic secret in .env constructed at runtime
    fake_token = "AK" + "IA" + "TEST1234567890"
    (proj_dir / ".env").write_text(f"API_KEY={fake_token}\n", encoding="utf-8")

    # Register & scan project
    project = repo.create_project("Target Project", str(proj_dir))
    scanner = FileScanner(repo=repo)
    scanner.scan_project(project["id"])

    app = create_app()
    client = TestClient(app)

    yield {
        "client": client,
        "repo": repo,
        "project_id": project["id"],
        "project_dir": proj_dir,
    }

    # Teardown
    if old_data_dir is not None:
        os.environ["SVANT_DATA_DIR"] = old_data_dir
    if old_local_only is not None:
        os.environ["SVANT_LOCAL_ONLY_MODE"] = old_local_only


def test_analyze_and_get_health(test_env):
    client: TestClient = test_env["client"]
    project_id = test_env["project_id"]

    # 1. Trigger analysis
    resp = client.post(f"/api/projects/{project_id}/analyze")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "success"
    assert "overall_score" in data
    assert "grade" in data
    assert data["findings_count"] > 0

    # 2. Query health
    h_resp = client.get(f"/api/projects/{project_id}/health")
    assert h_resp.status_code == 200, h_resp.text
    h_data = h_resp.json()
    assert h_data["project_id"] == project_id
    assert h_data["overall_score"] == data["overall_score"]
    assert "component_scores" in h_data
    assert "security" in h_data["component_scores"]
    assert "quality" in h_data["component_scores"]


def test_findings_filtering_and_lifecycle(test_env):
    client: TestClient = test_env["client"]
    project_id = test_env["project_id"]

    # Analyze first
    client.post(f"/api/projects/{project_id}/analyze")

    # List all findings
    resp = client.get(f"/api/projects/{project_id}/findings")
    assert resp.status_code == 200
    all_findings = resp.json()
    assert len(all_findings) > 0

    # Filter by category = security
    sec_resp = client.get(f"/api/projects/{project_id}/findings?category=security")
    assert sec_resp.status_code == 200
    sec_findings = sec_resp.json()
    assert len(sec_findings) > 0
    assert all(f["category"] == "security" for f in sec_findings)

    # Test status lifecycle PATCH
    target_finding = sec_findings[0]
    finding_id = target_finding["id"]
    assert target_finding["status"] == "open"

    # Acknowledge
    ack_resp = client.patch(
        f"/api/projects/{project_id}/findings/{finding_id}",
        json={"status": "acknowledged"},
    )
    assert ack_resp.status_code == 200
    assert ack_resp.json()["status"] == "acknowledged"

    # Resolve
    res_resp = client.patch(
        f"/api/projects/{project_id}/findings/{finding_id}",
        json={"status": "resolved"},
    )
    assert res_resp.status_code == 200
    assert res_resp.json()["status"] == "resolved"


def test_recommendations_and_duplicates_endpoints(test_env):
    client: TestClient = test_env["client"]
    project_id = test_env["project_id"]

    client.post(f"/api/projects/{project_id}/analyze")

    # Recommendations
    rec_resp = client.get(f"/api/projects/{project_id}/recommendations")
    assert rec_resp.status_code == 200
    rec_data = rec_resp.json()
    assert "recommendations_by_tier" in rec_data
    tiers = rec_data["recommendations_by_tier"]
    assert "fix_first" in tiers
    assert "should_fix" in tiers

    # Duplicates
    dup_resp = client.get(f"/api/projects/{project_id}/duplicates")
    assert dup_resp.status_code == 200
    dup_data = dup_resp.json()
    assert len(dup_data) >= 1
    cluster = dup_data[0]
    assert cluster["count"] >= 2
    assert cluster["wasted_bytes"] > 0
    assert len(cluster["files"]) >= 2

    # Statistics
    stat_resp = client.get(f"/api/projects/{project_id}/statistics")
    assert stat_resp.status_code == 200
    stat_data = stat_resp.json()
    assert stat_data["total_files"] > 0
    assert "Python" in stat_data["languages"]


def test_ai_actions_summarize_plan_explain(test_env):
    client: TestClient = test_env["client"]
    project_id = test_env["project_id"]

    client.post(f"/api/projects/{project_id}/analyze")

    # 1. Summarize
    sum_resp = client.post(f"/api/projects/{project_id}/ai/summarize")
    assert sum_resp.status_code == 200
    sum_data = sum_resp.json()
    assert sum_data["action"] == "summarize"
    assert "Executive Project Summary" in sum_data["content"] or "Target Project" in sum_data["content"]

    # 2. Plan
    plan_resp = client.post(f"/api/projects/{project_id}/ai/plan")
    assert plan_resp.status_code == 200
    plan_data = plan_resp.json()
    assert plan_data["action"] == "plan"
    assert "Phase 1" in plan_data["content"]

    # 3. Explain Finding
    findings = client.get(f"/api/projects/{project_id}/findings").json()
    first_finding = findings[0]

    exp_resp = client.post(f"/api/projects/{project_id}/ai/explain-finding/{first_finding['id']}")
    assert exp_resp.status_code == 200
    exp_data = exp_resp.json()
    assert exp_data["action"] == "explain_finding"
    assert first_finding["title"] in exp_data["content"]
    assert "Recommended Fix" in exp_data["content"] or "Analysis" in exp_data["content"]


def test_rag_chat_grounded_in_health(test_env):
    client: TestClient = test_env["client"]
    project_id = test_env["project_id"]

    client.post(f"/api/projects/{project_id}/analyze")

    # Ask chat about project health
    chat_resp = client.post(
        "/api/chat",
        json={
            "project_id": project_id,
            "message": "What is the health score, security status, and findings for this project?",
            "search_mode": "keyword",
        },
    )
    assert chat_resp.status_code == 200
    chat_data = chat_resp.json()

    # Grounded answer contains health information or citations to finding files
    assert "Health" in chat_data["answer"] or len(chat_data["sources"]) > 0
    # In Local Only mode, answer provides the evidence sources preview
    assert chat_data["provider"] == "local"
    assert chat_data["context_count"] > 0
