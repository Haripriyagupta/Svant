"""
Unit tests for ProjectIntelligenceEngine (Phase 4 & 5).
Validates concurrency protection, execution lifecycle, database persistence,
and finding deduplication via deterministic fingerprint.
"""

from __future__ import annotations

import os
from pathlib import Path
import pytest

from svant.core.intelligence.analyzer import ProjectIntelligenceEngine
from svant.core.scanner import FileScanner
from svant.db.connection import DatabaseManager
from svant.db.repository import Repository


@pytest.fixture
def repo(tmp_path: Path) -> Repository:
    db_file = tmp_path / "svant_engine_test.db"
    db_mgr = DatabaseManager(db_file)
    return Repository(db_mgr)


@pytest.fixture
def test_project(repo: Repository, tmp_path: Path):
    proj_dir = tmp_path / "engine_test_project"
    proj_dir.mkdir()

    src = proj_dir / "src"
    src.mkdir()
    (src / "main.py").write_text("print('test')\n", encoding="utf-8")
    (proj_dir / "README.md").write_text("# Project\n", encoding="utf-8")

    project = repo.create_project("Engine Test", str(proj_dir))
    scanner = FileScanner(repo=repo)
    scanner.scan_project(project["id"])
    return project["id"]


def test_engine_run_analysis_lifecycle(repo: Repository, test_project: str):
    engine = ProjectIntelligenceEngine(repo=repo)

    # 1. Run analysis
    res = engine.run_analysis(test_project)

    assert res["project_id"] == test_project
    assert "health" in res
    assert "findings" in res
    assert "inventory" in res
    assert "structure" in res

    # 2. Verify database records
    health_record = repo.get_project_health(test_project)
    assert health_record is not None
    assert health_record["overall_score"] == res["health"]["overall_score"]

    latest_run = repo.get_latest_analysis_run(test_project)
    assert latest_run is not None
    assert latest_run["status"] == "completed"

    findings = repo.list_findings(test_project)
    assert len(findings) == len(res["findings"])


def test_engine_deterministic_deduplication(repo: Repository, test_project: str):
    engine = ProjectIntelligenceEngine(repo=repo)

    # First run
    res1 = engine.run_analysis(test_project)
    count1 = len(repo.list_findings(test_project))

    # Second run immediately after
    res2 = engine.run_analysis(test_project)
    count2 = len(repo.list_findings(test_project))

    # Row count should be identical due to fingerprint UPSERT deduplication
    assert count1 == count2
    assert count1 == len(res1["findings"])
    assert count2 == len(res2["findings"])


def test_engine_concurrency_lock(repo: Repository, test_project: str):
    engine = ProjectIntelligenceEngine(repo=repo)

    lock = engine._get_project_lock(test_project)
    # Simulate an active analysis run by acquiring the lock
    acquired = lock.acquire(blocking=False)
    assert acquired is True

    try:
        # Second run should raise RuntimeError
        with pytest.raises(RuntimeError, match="already in progress"):
            engine.run_analysis(test_project)
    finally:
        lock.release()
