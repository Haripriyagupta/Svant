"""
Tests for incremental indexing pipeline in SVANT Phase 2.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from svant.core.embeddings import MockEmbeddingProvider
from svant.core.indexing import IndexingPipeline
from svant.core.scanner import FileScanner
from svant.core.vector_store import FAISSVectorStore, get_project_index_path
from svant.db.connection import DatabaseManager
from svant.db.repository import Repository


@pytest.fixture
def temp_env(tmp_path: Path):
    db_file = tmp_path / "test.db"
    db_manager = DatabaseManager(db_file)
    repo = Repository(db_manager)
    mock_provider = MockEmbeddingProvider(dimension=32)
    pipeline = IndexingPipeline(repo=repo, embedding_provider=mock_provider)
    scanner = FileScanner(repo=repo)
    return {
        "tmp_path": tmp_path,
        "repo": repo,
        "pipeline": pipeline,
        "scanner": scanner,
        "provider": mock_provider,
    }


def test_initial_project_indexing(temp_env):
    tmp_path = temp_env["tmp_path"]
    repo = temp_env["repo"]
    scanner = temp_env["scanner"]
    pipeline = temp_env["pipeline"]

    # Create dummy project files
    proj_dir = tmp_path / "my_project"
    proj_dir.mkdir()
    (proj_dir / "readme.md").write_text("# Project Title\nThis is a local intelligence platform.", encoding="utf-8")
    (proj_dir / "main.py").write_text("def start():\n    print('Running engine')\n", encoding="utf-8")

    # 1. Register project
    proj = repo.create_project(name="TestProj", root_path=str(proj_dir))
    pid = proj["id"]

    # 2. Scan project
    scan_summary = scanner.scan_project(pid, extract_text=True)
    assert scan_summary.total_scanned == 2

    # 3. Index project
    idx_summary = pipeline.index_project(pid)
    assert idx_summary.indexed_files == 2
    assert idx_summary.skipped_files == 0
    assert idx_summary.total_chunks >= 2
    assert idx_summary.total_vectors == idx_summary.total_chunks

    # Verify status recorded in SQLite
    status = repo.get_project_index_status(pid)
    assert status is not None
    assert status["status"] == "indexed"
    assert status["total_chunks"] == idx_summary.total_chunks
    assert status["total_vectors"] == idx_summary.total_vectors


def test_incremental_indexing_skips_unchanged(temp_env):
    tmp_path = temp_env["tmp_path"]
    repo = temp_env["repo"]
    scanner = temp_env["scanner"]
    pipeline = temp_env["pipeline"]

    proj_dir = tmp_path / "proj_inc"
    proj_dir.mkdir()
    (proj_dir / "doc1.txt").write_text("Document one with static unchanging content.", encoding="utf-8")
    (proj_dir / "doc2.txt").write_text("Document two with different static content.", encoding="utf-8")

    proj = repo.create_project(name="IncProj", root_path=str(proj_dir))
    pid = proj["id"]

    scanner.scan_project(pid, extract_text=True)
    res1 = pipeline.index_project(pid)
    assert res1.indexed_files == 2
    assert res1.skipped_files == 0

    # Second index run without changing files -> should skip all
    res2 = pipeline.index_project(pid)
    assert res2.indexed_files == 0
    assert res2.skipped_files == 2
    assert res2.total_chunks == res1.total_chunks


def test_incremental_indexing_reindexes_changed_file(temp_env):
    tmp_path = temp_env["tmp_path"]
    repo = temp_env["repo"]
    scanner = temp_env["scanner"]
    pipeline = temp_env["pipeline"]

    proj_dir = tmp_path / "proj_mod"
    proj_dir.mkdir()
    f1 = proj_dir / "file1.txt"
    f2 = proj_dir / "file2.txt"
    f1.write_text("Original text for file 1.", encoding="utf-8")
    f2.write_text("Original text for file 2.", encoding="utf-8")

    proj = repo.create_project(name="ModProj", root_path=str(proj_dir))
    pid = proj["id"]

    scanner.scan_project(pid, extract_text=True)
    res1 = pipeline.index_project(pid)
    initial_chunks = res1.total_chunks

    # Modify file 1
    f1.write_text("Completely updated text for file 1 with new information.", encoding="utf-8")
    # Rescan to update file hash in DB
    scanner.scan_project(pid, extract_text=True)

    # Re-index
    res2 = pipeline.index_project(pid)
    assert res2.indexed_files == 1  # Only file 1 was re-indexed!
    assert res2.skipped_files == 1  # File 2 was skipped


def test_force_rebuild_index(temp_env):
    tmp_path = temp_env["tmp_path"]
    repo = temp_env["repo"]
    scanner = temp_env["scanner"]
    pipeline = temp_env["pipeline"]

    proj_dir = tmp_path / "proj_rebuild"
    proj_dir.mkdir()
    (proj_dir / "test.txt").write_text("Some text for testing rebuild.", encoding="utf-8")

    proj = repo.create_project(name="RebuildProj", root_path=str(proj_dir))
    pid = proj["id"]

    scanner.scan_project(pid, extract_text=True)
    pipeline.index_project(pid)

    # Force rebuild
    rebuild_res = pipeline.index_project(pid, force_rebuild=True)
    assert rebuild_res.indexed_files == 1
    assert rebuild_res.skipped_files == 0
    assert rebuild_res.total_chunks >= 1
