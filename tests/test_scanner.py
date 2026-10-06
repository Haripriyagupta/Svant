"""
Tests for File Scanner and Search Service integration.
"""

from pathlib import Path
import pytest
from svant.db.connection import DatabaseManager
from svant.db.repository import Repository
from svant.core.scanner import FileScanner
from svant.core.search import SearchService, SearchMode


@pytest.fixture
def repo(tmp_path: Path) -> Repository:
    db_file = tmp_path / "scanner_test.db"
    return Repository(DatabaseManager(db_file))


def test_scanner_traversal_and_exclusions(repo: Repository, tmp_path: Path):
    proj_root = tmp_path / "sample_project"
    proj_root.mkdir()

    # Normal files
    (proj_root / "main.py").write_text("print('core logic here')", encoding="utf-8")
    (proj_root / "README.md").write_text("# Project Documentation\nWelcome to our sample app.", encoding="utf-8")

    # Subdirectory
    sub_dir = proj_root / "src"
    sub_dir.mkdir()
    (sub_dir / "utils.py").write_text("def calculate_metrics(): return 42", encoding="utf-8")

    # Excluded directories (.git, node_modules)
    git_dir = proj_root / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text("should_be_ignored = true", encoding="utf-8")

    node_modules_dir = proj_root / "node_modules"
    node_modules_dir.mkdir()
    (node_modules_dir / "package.json").write_text("{}", encoding="utf-8")

    # Create project in DB
    proj = repo.create_project("Sample Project", str(proj_root))

    # Run scanner
    scanner = FileScanner(repo=repo)
    summary = scanner.scan_project(proj["id"])

    # Excluded directories should NOT be scanned (should scan 3 files: main.py, README.md, src/utils.py)
    assert summary.total_scanned == 3
    assert summary.indexed_count == 3

    # Check files in database
    files = repo.list_files(project_id=proj["id"])
    assert len(files) == 3
    rel_paths = {f["relative_path"] for f in files}
    assert "main.py" in rel_paths
    assert "README.md" in rel_paths
    assert "src/utils.py" in rel_paths
    assert not any(".git" in p for p in rel_paths)
    assert not any("node_modules" in p for p in rel_paths)

    # Search keyword
    search_service = SearchService(repo=repo)
    hits = search_service.search("calculate_metrics", project_id=proj["id"])
    assert len(hits) == 1
    assert hits[0]["filename"] == "utils.py"
    assert "calculate_metrics" in hits[0]["snippet"]

    # Test rescan after file removal (stale file cleanup)
    (sub_dir / "utils.py").unlink()
    rescan_summary = scanner.scan_project(proj["id"])
    assert rescan_summary.total_scanned == 2
    assert repo.count_files(project_id=proj["id"]) == 2
    # Verify utils.py was deleted from search
    assert len(search_service.search("calculate_metrics", project_id=proj["id"])) == 0
