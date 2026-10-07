"""
Tests for Keyword, Semantic, and Hybrid search modes in SVANT Phase 2.
"""

from __future__ import annotations

from pathlib import Path
import pytest

from svant.core.embeddings import MockEmbeddingProvider
from svant.core.indexing import IndexingPipeline
from svant.core.scanner import FileScanner
from svant.core.search import SearchMode, SearchService
from svant.db.connection import DatabaseManager
from svant.db.repository import Repository


@pytest.fixture
def search_fixture(tmp_path: Path):
    db_file = tmp_path / "search_test.db"
    db_mgr = DatabaseManager(db_file)
    repo = Repository(db_mgr)
    provider = MockEmbeddingProvider(dimension=32)
    scanner = FileScanner(repo=repo)
    pipeline = IndexingPipeline(repo=repo, embedding_provider=provider)
    service = SearchService(repo=repo, embedding_provider=provider)

    # Setup project with sample knowledge files
    pdir = tmp_path / "codebase"
    pdir.mkdir()
    (pdir / "auth.py").write_text(
        "def authenticate_user(username, token):\n    '''Validate security tokens for local user.'''\n    return token == 'secret'\n",
        encoding="utf-8",
    )
    (pdir / "database.py").write_text(
        "def connect_sqlite():\n    '''Initialize SQLite database connection with WAL mode.'''\n    pass\n",
        encoding="utf-8",
    )
    (pdir / "notes.md").write_text(
        "# Deployment Guide\nPython virtual environments isolate project dependencies.\n",
        encoding="utf-8",
    )

    proj = repo.create_project(name="SearchTestProject", root_path=str(pdir))
    pid = proj["id"]

    scanner.scan_project(pid, extract_text=True)
    pipeline.index_project(pid)

    return {
        "repo": repo,
        "service": service,
        "project_id": pid,
        "provider": provider,
    }


def test_keyword_search_mode(search_fixture):
    service = search_fixture["service"]
    pid = search_fixture["project_id"]

    results = service.search("authenticate", project_id=pid, mode=SearchMode.KEYWORD)
    assert len(results) > 0
    assert results[0]["filename"] == "auth.py"
    assert results[0]["match_mode"] == "keyword"


def test_semantic_search_mode(search_fixture):
    service = search_fixture["service"]
    pid = search_fixture["project_id"]

    # Semantic search with natural language query
    results = service.search(
        "validate security tokens for user",
        project_id=pid,
        mode=SearchMode.SEMANTIC,
    )
    assert len(results) > 0
    # Top result should be the matching chunk
    assert any("auth.py" in r["filename"] for r in results)
    top_hit = results[0]
    assert "score" in top_hit
    assert top_hit["match_mode"] == "semantic"
    assert top_hit["chunk_id"] is not None


def test_hybrid_search_mode(search_fixture):
    service = search_fixture["service"]
    pid = search_fixture["project_id"]

    results = service.search(
        "SQLite database connection",
        project_id=pid,
        mode=SearchMode.HYBRID,
    )
    assert len(results) > 0
    top = results[0]
    assert "database.py" in top["filename"]
    assert "hybrid" in top["match_mode"]
    assert 0.0 <= top["score"] <= 1.0


def test_search_empty_query(search_fixture):
    service = search_fixture["service"]
    pid = search_fixture["project_id"]
    assert service.search("", project_id=pid, mode=SearchMode.KEYWORD) == []
    assert service.search("   ", project_id=pid, mode=SearchMode.SEMANTIC) == []
    assert service.search("", project_id=pid, mode=SearchMode.HYBRID) == []
