"""
Tests for SVANT Database layer, schema, and repository operations.
Uses temporary SQLite database files.
"""

from pathlib import Path
import pytest
from svant.db.connection import DatabaseManager
from svant.db.repository import Repository


@pytest.fixture
def repo(tmp_path: Path) -> Repository:
    db_file = tmp_path / "test_svant.db"
    db_mgr = DatabaseManager(db_file)
    return Repository(db_mgr)


def test_project_crud(repo: Repository, tmp_path: Path):
    project_dir = tmp_path / "my_project"
    project_dir.mkdir()

    # 1. Create project
    proj = repo.create_project("My Project", str(project_dir))
    assert proj["id"] is not None
    assert proj["name"] == "My Project"
    assert proj["root_path"] == str(project_dir)
    assert proj["status"] == "ready"

    # 2. Retrieve project
    retrieved = repo.get_project(proj["id"])
    assert retrieved is not None
    assert retrieved["name"] == "My Project"

    # 3. Retrieve by path
    by_path = repo.get_project_by_path(str(project_dir))
    assert by_path is not None
    assert by_path["id"] == proj["id"]

    # 4. List projects
    projs = repo.list_projects()
    assert len(projs) == 1

    # 5. Update project
    repo.update_project(proj["id"], status="scanned", file_count=10, total_size_bytes=1024)
    updated = repo.get_project(proj["id"])
    assert updated["status"] == "scanned"
    assert updated["file_count"] == 10
    assert updated["total_size_bytes"] == 1024

    # 6. Delete project
    deleted = repo.delete_project(proj["id"])
    assert deleted is True
    assert repo.get_project(proj["id"]) is None
    # Verify directory on disk was untouched
    assert project_dir.exists()


def test_file_and_fts_indexing(repo: Repository, tmp_path: Path):
    proj_dir = tmp_path / "codebase"
    proj_dir.mkdir()
    proj = repo.create_project("Codebase", str(proj_dir))

    # Upsert file
    file_path = str(proj_dir / "app.py")
    file_record = repo.upsert_file(
        project_id=proj["id"],
        path=file_path,
        relative_path="app.py",
        filename="app.py",
        extension=".py",
        category="source",
        size_bytes=256,
        modified_time="2026-10-07T00:00:00Z",
    )
    assert file_record["id"] is not None

    # Upsert extraction
    content = "def authenticate_user(username, password): return True"
    repo.upsert_extraction(
        file_id=file_record["id"],
        project_id=proj["id"],
        content_text=content,
        char_count=len(content),
        status="extracted",
    )

    # Index in FTS5
    repo.index_file_fts(
        file_id=file_record["id"],
        project_id=proj["id"],
        filename="app.py",
        relative_path="app.py",
        content=content,
    )

    # Search FTS5
    results = repo.search_fts("authenticate")
    assert len(results) == 1
    assert results[0]["file_id"] == file_record["id"]
    assert "authenticate" in results[0]["snippet"].lower()

    # Search non-matching
    no_results = repo.search_fts("nonexistent_term_xyz")
    assert len(no_results) == 0

    # Project deletion cascades to FTS and files
    repo.delete_project(proj["id"])
    assert repo.search_fts("authenticate") == []
    assert repo.get_file(file_record["id"]) is None
