"""
Security & Privacy Regression Tests for SVANT Assistant & RAG (Phase 6 & 7).
Ensures zero raw credentials ever leak to any AI provider, prompt, or response.
Constructs synthetic tokens dynamically at runtime to guarantee GitHub secret scanning safety.
"""

from __future__ import annotations

import pytest
from pathlib import Path
from starlette.testclient import TestClient

from svant.api.app import create_app
from svant.config import settings
from svant.core.ai.factory import set_active_ai_provider
from svant.core.ai.mock import MockAIProvider
from svant.core.assistant import ProjectAssistant
from svant.core.rag.pipeline import RAGPipeline
from svant.core.search import SearchMode, SearchService
from svant.db.connection import DatabaseManager
import svant.db.connection as db_conn
from svant.db.repository import Repository


@pytest.fixture
def privacy_test_env(tmp_path: Path):
    db_file = tmp_path / "privacy_test.db"
    settings.db_path = db_file
    settings.data_dir = tmp_path

    db_mgr = DatabaseManager(db_file)
    db_conn._default_manager = db_mgr
    repo = Repository(db_mgr)

    # Dynamically constructed synthetic credentials (zero literal secrets in code)
    fake_aws_prefix = "AK" + "IA"
    synthetic_aws_key = fake_aws_prefix + "1234567890123456"

    fake_gh_prefix = "gh" + "p_"
    synthetic_gh_token = fake_gh_prefix + "123456789012345678901234567890123456"

    proj_dir = tmp_path / "credential_vault"
    proj_dir.mkdir()
    (proj_dir / "cloud.py").write_text(
        f'AWS_ACCESS_KEY_ID = "{synthetic_aws_key}"\nGITHUB_TOKEN = "{synthetic_gh_token}"\n',
        encoding="utf-8",
    )
    (proj_dir / ".env").write_text(f'API_KEY="{synthetic_aws_key}"\n', encoding="utf-8")
    (proj_dir / "README.md").write_text("# Vault Project\nHandles external integrations.\n", encoding="utf-8")

    app = create_app()
    client = TestClient(app)
    add_resp = client.post("/api/projects", json={"path": str(proj_dir), "name": "Vault"})
    assert add_resp.status_code == 201
    proj_id = add_resp.json()["id"]

    # Scan and index
    client.post(f"/api/projects/{proj_id}/scan")
    client.post(f"/api/projects/{proj_id}/index")
    client.post(f"/api/projects/{proj_id}/analyze")

    return {
        "client": client,
        "repo": repo,
        "project_id": proj_id,
        "synthetic_aws_key": synthetic_aws_key,
        "synthetic_gh_token": synthetic_gh_token,
    }


def test_ai_provider_never_receives_raw_secrets(privacy_test_env):
    """
    Critical Regression Test:
    raw secret -> scanner -> finding/context -> AI pipeline
    Verifies that raw secrets are intercepted and redacted before reaching the AI provider.
    """
    repo = privacy_test_env["repo"]
    proj_id = privacy_test_env["project_id"]
    synth_aws = privacy_test_env["synthetic_aws_key"]
    synth_gh = privacy_test_env["synthetic_gh_token"]

    mock_provider = MockAIProvider()
    set_active_ai_provider(mock_provider)

    try:
        search_svc = SearchService(repo)
        pipeline = RAGPipeline(repo=repo, search_service=search_svc, ai_provider=mock_provider)

        # Query asking directly about credentials in cloud.py
        rag_res = pipeline.query(
            project_id=proj_id,
            message="What is the AWS_ACCESS_KEY_ID configured in cloud.py?",
            search_mode=SearchMode.HYBRID,
            provider_name="mock",
        )

        assert len(mock_provider.call_history) == 1
        call = mock_provider.call_history[0]
        context_sent = call["context"]
        user_prompt_sent = call["user_prompt"]

        # ZERO RAW SECRETS IN CONTEXT OR PROMPTS
        assert synth_aws not in context_sent, "RAW AWS KEY LEAKED TO AI PROVIDER CONTEXT!"
        assert synth_gh not in context_sent, "RAW GITHUB TOKEN LEAKED TO AI PROVIDER CONTEXT!"
        assert synth_aws not in user_prompt_sent, "RAW AWS KEY LEAKED TO USER PROMPT!"
        assert synth_gh not in user_prompt_sent, "RAW GITHUB TOKEN LEAKED TO USER PROMPT!"

        # REDACTION MARKER IS PRESENT
        assert "[REDACTED:AWS_KEY_ID]" in context_sent or "[REDACTED:CREDENTIAL]" in context_sent
        assert rag_res.redactions >= 1

        # Check citations
        for cit in rag_res.sources:
            assert synth_aws not in cit.snippet_preview
            assert synth_gh not in cit.snippet_preview

    finally:
        set_active_ai_provider(None)


def test_project_assistant_redacts_secrets_in_findings(privacy_test_env):
    """
    Verifies ProjectAssistant.explain_finding masks credentials in evidence and citations.
    """
    client: TestClient = privacy_test_env["client"]
    proj_id = privacy_test_env["project_id"]
    synth_aws = privacy_test_env["synthetic_aws_key"]

    findings = client.get(f"/api/projects/{proj_id}/findings?category=security").json()
    assert len(findings) > 0

    target_f = next((f for f in findings if "AWS" in f["title"] or "cloud.py" in str(f.get("relative_path"))), findings[0])

    exp_resp = client.post(f"/api/projects/{proj_id}/ai/explain-finding/{target_f['id']}")
    assert exp_resp.status_code == 200
    exp_data = exp_resp.json()

    # Raw secret must NEVER appear in the explanation output
    assert synth_aws not in exp_data["content"]
    assert "[REDACTED" in exp_data["content"]

    # Raw secret must NEVER appear in returned citation snippets
    for source in exp_data.get("sources", []):
        assert synth_aws not in source["snippet_preview"]
