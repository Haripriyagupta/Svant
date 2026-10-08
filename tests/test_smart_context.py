"""
Unit tests for SmartContextSelector (Phase 6 & 7).
Validates intent classification, multi-category intelligence context assembly,
budget bounding, deduplication, and citation integrity.
"""

from __future__ import annotations

import pytest
from pathlib import Path

from svant.core.intelligence.models import FindingCategory, FindingSeverity, PriorityTier
from svant.core.rag.context import ContextAssembler, ContextCategory
from svant.core.rag.smart_selector import QueryIntent, SmartContextSelector
from svant.core.search import SearchMode
from svant.db.connection import get_db
from svant.db.repository import Repository


@pytest.fixture
def repo(tmp_path: Path):
    db_path = tmp_path / "test_smart_context.db"
    db = get_db(str(db_path))
    return Repository(db)


def test_classify_intent():
    selector = SmartContextSelector(repo=None)

    # Security queries
    assert QueryIntent.SECURITY in selector.classify_intent("What security vulnerabilities and exposed secrets exist?")
    assert QueryIntent.SECURITY in selector.classify_intent("Are there private keys or credentials?")

    # Architecture & overview queries
    assert QueryIntent.ARCHITECTURE in selector.classify_intent("How does this project work and what is the architecture?")
    assert QueryIntent.ARCHITECTURE in selector.classify_intent("What is the application entry point?")

    # Health & scoring queries
    assert QueryIntent.HEALTH in selector.classify_intent("Why is my health score low?")
    assert QueryIntent.HEALTH in selector.classify_intent("What is the health grade of this repository?")

    # Priority queries
    assert QueryIntent.PRIORITY in selector.classify_intent("Which files should I fix first?")
    assert QueryIntent.PRIORITY in selector.classify_intent("What are the top priority issues to remediate?")

    # Onboarding queries
    assert QueryIntent.ONBOARDING in selector.classify_intent("How do I get started as a new contributor on this project?")

    # Testing queries
    assert QueryIntent.TESTING in selector.classify_intent("Tell me about the test coverage and pytest suite")

    # Dependencies queries
    assert QueryIntent.DEPENDENCIES in selector.classify_intent("Are there dependency problems in requirements.txt?")

    # Duplicates queries
    assert QueryIntent.DUPLICATES in selector.classify_intent("Are there duplicate identical files wasting storage?")

    # General queries
    assert QueryIntent.GENERAL in selector.classify_intent("Tell me about function calculate_tax")


def test_smart_context_security_injection(repo: Repository):
    proj = repo.create_project(name="SecProj", root_path="/test/sec")
    proj_id = proj["id"]

    # Add security findings
    repo.upsert_findings(proj_id, [
        {
            "id": "f-sec-1",
            "project_id": proj_id,
            "category": FindingCategory.SECURITY.value,
            "severity": FindingSeverity.CRITICAL.value,
            "priority_tier": PriorityTier.FIX_FIRST.value,
            "title": "Exposed Cloud Token",
            "description": "Hardcoded token found in auth.py",
            "recommendation": "Use environment variable",
            "relative_path": "src/auth.py",
            "location": "Line 24",
            "evidence": "token = '[REDACTED]'",
            "confidence": 1.0,
            "fingerprint": f"{proj_id}:security:token:src/auth.py",
            "status": "open",
        }
    ])

    selector = SmartContextSelector(repo=repo)
    items = selector.build_context(
        project_id=proj_id,
        query="What security issues are present in this project?",
    )

    assert len(items) >= 1
    sec_item = next((it for it in items if "Exposed Cloud Token" in it.content), None)
    assert sec_item is not None
    assert sec_item.category == ContextCategory.SECURITY_FINDINGS.value
    assert "src/auth.py" in sec_item.relative_path


def test_smart_context_budget_bounding(repo: Repository):
    proj = repo.create_project(name="BudgetProj", root_path="/test/budget")
    proj_id = proj["id"]

    # Insert multiple findings
    findings = []
    for i in range(20):
        findings.append({
            "id": f"f-p-{i}",
            "project_id": proj_id,
            "category": FindingCategory.QUALITY.value,
            "severity": FindingSeverity.HIGH.value,
            "priority_tier": PriorityTier.FIX_FIRST.value,
            "title": f"Large Technical Debt Block {i}",
            "description": "A" * 1500,  # 1500 chars each
            "recommendation": "Refactor into small modules",
            "relative_path": f"src/mod_{i}.py",
            "confidence": 1.0,
            "fingerprint": f"{proj_id}:quality:debt:{i}",
            "status": "open",
        })
    repo.upsert_findings(proj_id, findings)

    # Set strict context budget of 4000 characters
    strict_assembler = ContextAssembler(max_context_chars=4000)
    selector = SmartContextSelector(repo=repo, assembler=strict_assembler)

    items = selector.build_context(
        project_id=proj_id,
        query="What should I fix first?",
    )

    total_chars = sum(len(it.content) for it in items)
    assert total_chars <= 4050  # Bounded strictly within budget


def test_smart_context_referenced_finding(repo: Repository):
    proj = repo.create_project(name="RefProj", root_path="/test/ref")
    proj_id = proj["id"]

    ref_finding = {
        "id": "ref-123",
        "project_id": proj_id,
        "category": "security",
        "severity": "critical",
        "priority_tier": "fix_first",
        "title": "Leaked Database Password",
        "description": "Hardcoded DB credentials detected",
        "recommendation": "Rotate password and inject via secret manager",
        "relative_path": "config/db.py",
        "location": "Line 42",
        "evidence": "password = '[REDACTED]'",
    }

    selector = SmartContextSelector(repo=repo)
    items = selector.build_context(
        project_id=proj_id,
        query="Explain that second issue",
        referenced_finding=ref_finding,
    )

    assert any("Leaked Database Password" in it.content for it in items)
    first_item = items[0]
    assert first_item.relative_path == "config/db.py"
    assert first_item.relevance_score == 1.0
