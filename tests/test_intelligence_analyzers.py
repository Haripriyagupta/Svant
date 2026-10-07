"""
Unit tests for SVANT Intelligence Analyzers (Phase 4 & 5).
Validates Inventory, Structure, Security, Dependencies, Testing, Documentation,
Hygiene, and Quality analyzers.
Ensures ZERO raw secret exposure in findings and evidence.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from svant.core.classifier import FileClassifier
from svant.core.extractor import DocumentExtractor
from svant.core.intelligence.dependencies import DependencyAnalyzer
from svant.core.intelligence.documentation import DocumentationAnalyzer
from svant.core.intelligence.hygiene import HygieneAnalyzer
from svant.core.intelligence.inventory import ProjectInventoryBuilder
from svant.core.intelligence.models import FindingCategory, FindingSeverity, PriorityTier
from svant.core.intelligence.quality import QualityAnalyzer
from svant.core.intelligence.security import SecurityAnalyzer
from svant.core.intelligence.structure import ProjectStructureAnalyzer
from svant.core.intelligence.testing import TestingAnalyzer
from svant.core.privacy.redactor import SecretRedactor
from svant.core.scanner import FileScanner
from svant.db.connection import DatabaseManager
from svant.db.repository import Repository


@pytest.fixture
def repo(tmp_path: Path) -> Repository:
    db_file = tmp_path / "svant_test_intel.db"
    db_mgr = DatabaseManager(db_file)
    return Repository(db_mgr)


@pytest.fixture
def populated_project(repo: Repository, tmp_path: Path):
    """Creates a realistic project on disk and scans it into the repository."""
    proj_dir = tmp_path / "sample_codebase"
    proj_dir.mkdir()

    # 1. Structure: python source, tests, docs
    src_dir = proj_dir / "src"
    src_dir.mkdir()
    (src_dir / "__init__.py").write_text("", encoding="utf-8")

    # Monolithic source file with debug log and TODOs
    monolith_lines = ["# Monolithic source file\n"]
    for i in range(1010):
        if i == 50:
            monolith_lines.append("import pdb; pdb.set_trace()\n")
        elif 60 <= i < 68:
            monolith_lines.append(f"# TODO: Tech debt item {i}\n")
        else:
            monolith_lines.append(f"def func_{i}(): pass\n")
    (src_dir / "monolith.py").write_text("".join(monolith_lines), encoding="utf-8")

    # Insecure config file (verify=False and DEBUG=True)
    (src_dir / "config.py").write_text(
        "import requests\nDEBUG = True\nresponse = requests.get('https://example.com', verify=False)\n",
        encoding="utf-8",
    )

    # Additional source files to reach source_count >= 5
    (src_dir / "util1.py").write_text("def a(): pass\n", encoding="utf-8")
    (src_dir / "util2.py").write_text("def b(): pass\n", encoding="utf-8")
    (src_dir / "util3.py").write_text("def c(): pass\n", encoding="utf-8")

    # 2. Secret exposure in a tracked .env file
    # Synthetic tokens built at runtime to avoid static push protection triggers
    fake_aws_key = "AK" + "IA" + "1234567890ABCDEF"
    fake_openai_key = "sk-" + "proj-" + "1234567890abcdef1234567890abcdef12345"
    (proj_dir / ".env").write_text(
        f"DATABASE_URL=postgres://user:secret@localhost:5432/db\nAWS_ACCESS_KEY_ID={fake_aws_key}\nOPENAI_API_KEY={fake_openai_key}\n",
        encoding="utf-8",
    )

    # Private key file
    (proj_dir / "server.key").write_text("-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA...\n-----END RSA PRIVATE KEY-----", encoding="utf-8")

    # 3. Dependencies: requirements.txt with unpinned and duplicates
    (proj_dir / "requirements.txt").write_text(
        "fastapi==0.110.0\nuvicorn\nrequests==2.31.0\nfastapi\n",
        encoding="utf-8",
    )

    # 4. Docs: Brief README (<150 chars)
    (proj_dir / "README.md").write_text("# Sample\nA small project.", encoding="utf-8")

    # 5. Duplicate files (exact SHA-256 match)
    dup_content = "Identical duplicate file content for testing hygiene detection."
    (src_dir / "dup_a.txt").write_text(dup_content, encoding="utf-8")
    (src_dir / "dup_b.txt").write_text(dup_content, encoding="utf-8")

    # Temporary clutter file
    (proj_dir / "npm-debug.log").write_text("debug log output", encoding="utf-8")

    # Scan project
    project = repo.create_project(name="Sample Codebase", root_path=str(proj_dir))
    scanner = FileScanner(repo=repo)
    scanner.scan_project(project["id"])

    return project["id"], proj_dir


def test_inventory_builder(repo: Repository, populated_project):
    project_id, _ = populated_project
    builder = ProjectInventoryBuilder(repo)
    inv = builder.build_inventory(project_id)

    assert inv.total_files > 0
    assert inv.source_files >= 2
    assert "Python" in inv.languages
    assert len(inv.manifest_files) >= 1
    assert len(inv.doc_files) >= 1


def test_structure_analyzer(repo: Repository, populated_project):
    project_id, _ = populated_project
    files = repo.list_files(project_id)
    builder = ProjectInventoryBuilder(repo)
    inv = builder.build_inventory(project_id)

    analyzer = ProjectStructureAnalyzer()
    struct, findings = analyzer.analyze(project_id, inv, files)

    assert "python" in struct.detected_ecosystems
    assert any("src" in r for r in struct.source_roots)


def test_security_analyzer_zero_raw_secret_guarantee(repo: Repository, populated_project):
    project_id, _ = populated_project
    files = repo.list_files(project_id)

    redactor = SecretRedactor()
    analyzer = SecurityAnalyzer(repo, redactor)
    findings = analyzer.analyze(project_id, files)

    assert len(findings) > 0

    # Ensure sensitive .env and .key files were flagged
    titles = [f.title for f in findings]
    assert any("Sensitive credential or environment file tracked" in t for t in titles)
    assert any("private key" in t.lower() for t in titles)
    assert any("ssl/tls" in t.lower() for t in titles)

    # CRITICAL: Verify ZERO raw secret appears anywhere in findings
    for f in findings:
        assert "AK" + "IA" not in (f.evidence or "")
        assert "sk-proj-" not in (f.evidence or "")
        assert "AK" + "IA" not in f.description

    # Secret findings contain redacted tags
    secret_findings = [f for f in findings if "exposed secret" in f.title.lower()]
    assert len(secret_findings) > 0
    for sf in secret_findings:
        assert "[REDACTED:" in (sf.evidence or "")


def test_dependency_analyzer(repo: Repository, populated_project):
    project_id, _ = populated_project
    files = repo.list_files(project_id)

    analyzer = DependencyAnalyzer(repo)
    summary, findings = analyzer.analyze(project_id, files)

    assert summary["manifest_count"] >= 1
    titles = [f.title for f in findings]
    assert any("Unpinned" in t for t in titles)
    assert any("Duplicate" in t for t in titles)


def test_testing_analyzer(repo: Repository, populated_project):
    project_id, _ = populated_project
    files = repo.list_files(project_id)
    inv = ProjectInventoryBuilder(repo).build_inventory(project_id)
    struct, _ = ProjectStructureAnalyzer().analyze(project_id, inv, files)

    analyzer = TestingAnalyzer()
    metrics, findings = analyzer.analyze(project_id, inv, struct, files)

    assert metrics["test_files_count"] == 0
    assert any("No automated tests detected" in f.title for f in findings)


def test_documentation_analyzer(repo: Repository, populated_project):
    project_id, _ = populated_project
    files = repo.list_files(project_id)
    inv = ProjectInventoryBuilder(repo).build_inventory(project_id)
    struct, _ = ProjectStructureAnalyzer().analyze(project_id, inv, files)

    analyzer = DocumentationAnalyzer(repo)
    metrics, findings = analyzer.analyze(project_id, inv, struct, files)

    assert metrics["has_readme"] is True
    assert metrics["has_license"] is False
    titles = [f.title for f in findings]
    assert any("brief" in t.lower() or "missing" in t.lower() for t in titles)


def test_hygiene_analyzer(repo: Repository, populated_project):
    project_id, _ = populated_project
    files = repo.list_files(project_id)
    inv = ProjectInventoryBuilder(repo).build_inventory(project_id)

    analyzer = HygieneAnalyzer(repo)
    metrics, findings = analyzer.analyze(project_id, inv, files)

    assert metrics["duplicate_groups_count"] >= 1
    assert metrics["wasted_bytes"] > 0
    assert any("Duplicate" in f.title for f in findings)
    assert any("clutter" in f.title.lower() for f in findings)


def test_quality_analyzer(repo: Repository, populated_project):
    project_id, _ = populated_project
    files = repo.list_files(project_id)

    analyzer = QualityAnalyzer(repo)
    metrics, findings = analyzer.analyze(project_id, files)

    assert metrics["large_source_files_count"] >= 1
    assert metrics["total_todo_markers"] >= 6
    assert metrics["total_debug_statements"] >= 1

    titles = [f.title for f in findings]
    assert any("oversized source file" in t.lower() for t in titles)
    assert any("todo/fixme" in t.lower() for t in titles)
    assert any("debug" in t.lower() for t in titles)
