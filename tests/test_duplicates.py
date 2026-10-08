"""
Tests for Exact and Near-Duplicate Detection Engine in SVANT.
Verifies SHA-256 exact matching, SequenceMatcher text similarity,
exclusion rules, edge cases, and API endpoint responses.
"""

import os
from pathlib import Path
import pytest
from starlette.testclient import TestClient

from svant.api.app import create_app
from svant.config import settings
from svant.core.intelligence.duplicates import DuplicateDetector
from svant.core.scanner import FileScanner
from svant.db.connection import DatabaseManager
from svant.db.repository import Repository


@pytest.fixture
def dup_test_env(tmp_path: Path):
    """Sets up an isolated test project with exact and near duplicates."""
    data_dir = tmp_path / "svant_data"
    data_dir.mkdir()
    db_file = data_dir / "svant.db"

    os.environ["SVANT_DATA_DIR"] = str(data_dir)
    os.environ["SVANT_LOCAL_ONLY_MODE"] = "true"
    settings.data_dir = data_dir
    settings.db_path = db_file
    settings.local_only_mode = True

    db_mgr = DatabaseManager(db_file)
    import svant.db.connection as db_conn
    db_conn._default_manager = db_mgr
    repo = Repository(db_mgr)

    proj_dir = tmp_path / "test_dup_repo"
    proj_dir.mkdir()
    src = proj_dir / "src"
    src.mkdir()

    # 1. Exact duplicates: exact1.py and exact2.py (100% hash match)
    exact_code = (
        "def compute_hash(data: str) -> str:\n"
        "    import hashlib\n"
        "    return hashlib.sha256(data.encode('utf-8')).hexdigest()\n"
    )
    (src / "exact1.py").write_text(exact_code, encoding="utf-8")
    (src / "exact2.py").write_text(exact_code, encoding="utf-8")

    # 2. Near duplicates: service_v1.py and service_v2.py (~95% similar with minor edit)
    service_code_v1 = (
        "class AuthService:\n"
        "    def __init__(self, secret: str):\n"
        "        self.secret = secret\n"
        "\n"
        "    def authenticate(self, username: str, token: str) -> bool:\n"
        "        if not username or not token:\n"
        "            return False\n"
        "        return token == self.secret\n"
        "\n"
        "    def logout(self, user_id: str) -> None:\n"
        "        print(f'User {user_id} logged out')\n"
    )
    service_code_v2 = (
        "# Updated authentication service\n"
        "class AuthService:\n"
        "    def __init__(self, secret: str):\n"
        "        self.secret = secret\n"
        "\n"
        "    def authenticate(self, username: str, token: str) -> bool:\n"
        "        if not username or not token:\n"
        "            return False\n"
        "        return token == self.secret\n"
        "\n"
        "    def logout(self, user_id: str) -> None:\n"
        "        print(f'User {user_id} logged out successfully')\n"
    )
    (src / "service_v1.py").write_text(service_code_v1, encoding="utf-8")
    (src / "service_v2.py").write_text(service_code_v2, encoding="utf-8")

    # 3. Completely unrelated file: should NOT be grouped with anything
    unrelated_code = (
        "import sys\n"
        "def run_migrations():\n"
        "    print('Running DB migrations...')\n"
        "    sys.exit(0)\n"
    )
    (src / "migrations.py").write_text(unrelated_code, encoding="utf-8")

    # 4. Excluded directory file (e.g. node_modules/copy.py)
    nm_dir = proj_dir / "node_modules" / "somepkg"
    nm_dir.mkdir(parents=True)
    (nm_dir / "exact1_copy.py").write_text(exact_code, encoding="utf-8")

    # 5. Tiny file (< 20 bytes): should be skipped for similarity
    (src / "__init__.py").write_text("", encoding="utf-8")

    # Register and scan project
    project = repo.create_project("Duplicate Test Project", str(proj_dir))
    scanner = FileScanner(repo=repo, excluded_dirs=["node_modules"])
    scanner.scan_project(project["id"])

    app = create_app()
    client = TestClient(app)

    yield {
        "client": client,
        "repo": repo,
        "project_id": project["id"],
        "project_dir": proj_dir,
    }


def test_duplicate_detector_direct(dup_test_env):
    """Test DuplicateDetector directly on SQLite data."""
    repo = dup_test_env["repo"]
    project_id = dup_test_env["project_id"]

    detector = DuplicateDetector(repo=repo)
    clusters = detector.detect_duplicates(project_id)

    # Should have at least 2 clusters: 1 exact, 1 near-duplicate
    assert len(clusters) >= 2

    # Check exact duplicate cluster
    exact_clusters = [c for c in clusters if c["duplicate_type"] == "exact"]
    assert len(exact_clusters) == 1
    exact_c = exact_clusters[0]
    assert exact_c["similarity_pct"] == 100
    assert exact_c["similarity"] == 1.0
    assert exact_c["count"] == 2
    assert exact_c["wasted_bytes"] > 0
    assert exact_c["primary_file"] is not None
    assert exact_c["primary_file"]["role"] == "original"
    assert any(f["role"] == "copy" for f in exact_c["files"])
    exact_paths = [f["relative_path"] for f in exact_c["files"]]
    assert any("exact1.py" in p for p in exact_paths)
    assert any("exact2.py" in p for p in exact_paths)

    # Check near-duplicate cluster
    similar_clusters = [c for c in clusters if c["duplicate_type"] == "similar"]
    assert len(similar_clusters) >= 1
    sim_c = similar_clusters[0]
    assert 85 <= sim_c["similarity_pct"] <= 99
    assert sim_c["count"] == 2
    assert sim_c["wasted_bytes"] > 0
    sim_paths = [f["relative_path"] for f in sim_c["files"]]
    assert any("service_v1.py" in p for p in sim_paths)
    assert any("service_v2.py" in p for p in sim_paths)

    # Verify unrelated file is NOT part of any cluster
    all_clustered_paths = [f["relative_path"] for c in clusters for f in c["files"]]
    assert not any("migrations.py" in p for p in all_clustered_paths)


def test_duplicate_api_endpoint(dup_test_env):
    """Test GET /api/projects/{id}/duplicates endpoint."""
    client = dup_test_env["client"]
    project_id = dup_test_env["project_id"]

    resp = client.get(f"/api/projects/{project_id}/duplicates")
    assert resp.status_code == 200
    clusters = resp.json()

    assert len(clusters) >= 2
    for c in clusters:
        assert "duplicate_type" in c
        assert "similarity_pct" in c
        assert "count" in c
        assert "wasted_bytes" in c
        assert "files" in c
        assert len(c["files"]) >= 2
        assert c["primary_file"] is not None


def test_empty_and_single_file_project(tmp_path: Path):
    """Verify empty and single-file projects produce zero duplicate clusters gracefully."""
    data_dir = tmp_path / "svant_empty_data"
    data_dir.mkdir()
    db_file = data_dir / "svant.db"

    os.environ["SVANT_DATA_DIR"] = str(data_dir)
    settings.data_dir = data_dir
    settings.db_path = db_file

    db_mgr = DatabaseManager(db_file)
    repo = Repository(db_mgr)

    empty_proj_dir = tmp_path / "empty_repo"
    empty_proj_dir.mkdir()

    # Empty project
    project = repo.create_project("Empty Project", str(empty_proj_dir))
    detector = DuplicateDetector(repo=repo)
    assert detector.detect_duplicates(project["id"]) == []

    # Single-file project
    (empty_proj_dir / "solo.py").write_text("print('lone wolf')\n", encoding="utf-8")
    scanner = FileScanner(repo=repo)
    scanner.scan_project(project["id"])
    assert detector.detect_duplicates(project["id"]) == []
