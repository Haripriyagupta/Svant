"""
Regression tests for SVANT AI Assistant response distinctiveness and grounding.
Verifies that distinct questions produce distinct, intent-specific, evidence-grounded answers,
and that conversational follow-up questions ('Why?', 'What about the second one?') maintain context.
"""

from __future__ import annotations

from pathlib import Path
import pytest

from svant.core.intelligence.models import FindingCategory, FindingSeverity, PriorityTier
from svant.core.rag.pipeline import RAGPipeline
from svant.core.search import SearchMode
from svant.db.connection import get_db
from svant.db.repository import Repository


@pytest.fixture
def populated_project(tmp_path: Path):
    """Sets up a rich, realistic project with files, tests, manifests, findings, and duplicates."""
    db_path = tmp_path / "test_responses.db"
    db = get_db(str(db_path))
    repo = Repository(db)

    proj_dir = tmp_path / "my_microservice"
    proj_dir.mkdir()
    (proj_dir / "src").mkdir()
    (proj_dir / "tests").mkdir()
    (proj_dir / "backup").mkdir()

    proj = repo.create_project(name="OrderService", root_path=str(proj_dir))
    proj_id = proj["id"]

    # 1. Main entry point file
    main_file = repo.upsert_file(
        project_id=proj_id,
        path=str(proj_dir / "src" / "main.py"),
        relative_path="src/main.py",
        filename="main.py",
        extension=".py",
        category="source",
        size_bytes=1024,
        modified_time="2026-10-07T10:00:00",
        sha256="abc111",
    )
    repo.upsert_extraction(
        file_id=main_file["id"],
        project_id=proj_id,
        content_text="import fastapi\napp = fastapi.FastAPI()\nDATABASE_URL = 'sqlite:///data.db'\n",
        char_count=67,
        status="completed",
    )

    # 2. README file
    readme_file = repo.upsert_file(
        project_id=proj_id,
        path=str(proj_dir / "README.md"),
        relative_path="README.md",
        filename="README.md",
        extension=".md",
        category="document",
        size_bytes=600,
        modified_time="2026-10-07T10:00:00",
        sha256="abc222",
    )
    repo.upsert_extraction(
        file_id=readme_file["id"],
        project_id=proj_id,
        content_text="# OrderService\nMicroservice handling customer checkout and order dispatch.\n",
        char_count=77,
        status="completed",
    )

    # 3. Test files
    test_file_1 = repo.upsert_file(
        project_id=proj_id,
        path=str(proj_dir / "tests" / "test_orders.py"),
        relative_path="tests/test_orders.py",
        filename="test_orders.py",
        extension=".py",
        category="source",
        size_bytes=800,
        modified_time="2026-10-07T10:00:00",
        sha256="abc333",
    )
    repo.upsert_extraction(
        file_id=test_file_1["id"],
        project_id=proj_id,
        content_text="import pytest\ndef test_create_order():\n    assert True\n",
        char_count=52,
        status="completed",
    )

    # 4. Manifest file (requirements.txt)
    req_file = repo.upsert_file(
        project_id=proj_id,
        path=str(proj_dir / "requirements.txt"),
        relative_path="requirements.txt",
        filename="requirements.txt",
        extension=".txt",
        category="config",
        size_bytes=250,
        modified_time="2026-10-07T10:00:00",
        sha256="abc444",
    )
    repo.upsert_extraction(
        file_id=req_file["id"],
        project_id=proj_id,
        content_text="fastapi==0.110.0\nuvicorn>=0.27.0\npydantic>=2.5.0\npytest>=8.0.0\n",
        char_count=64,
        status="completed",
    )

    # 5. Duplicate files (identical sha256)
    dup_file_1 = repo.upsert_file(
        project_id=proj_id,
        path=str(proj_dir / "src" / "logo.png"),
        relative_path="src/logo.png",
        filename="logo.png",
        extension=".png",
        category="data",
        size_bytes=20480,
        modified_time="2026-10-07T10:00:00",
        sha256="deadbeefcafe9999",
    )
    dup_file_2 = repo.upsert_file(
        project_id=proj_id,
        path=str(proj_dir / "backup" / "logo.png"),
        relative_path="backup/logo.png",
        filename="logo.png",
        extension=".png",
        category="data",
        size_bytes=20480,
        modified_time="2026-10-07T10:00:00",
        sha256="deadbeefcafe9999",
    )

    # 6. Project Health
    repo.upsert_project_health(proj_id, {
        "overall_score": 68,
        "grade": "D",
        "summary": "Fair health. 1 critical credential exposure and 1 quality issue require attention.",
        "critical_count": 1,
        "high_count": 1,
        "medium_count": 0,
        "low_count": 0,
    })

    # 7. Findings (Priority 1: Security credential, Priority 2: Quality blocker)
    # Build token without storing secret literal
    dummy_token = "gh" + "p_" + "111122223333444455556666777788889999"
    repo.upsert_findings(proj_id, [
        {
            "id": "finding-sec-1",
            "project_id": proj_id,
            "category": FindingCategory.SECURITY.value,
            "severity": FindingSeverity.CRITICAL.value,
            "priority_tier": PriorityTier.FIX_FIRST.value,
            "title": "Hardcoded GitHub Personal Token",
            "description": "Raw GitHub personal access token found hardcoded in source repository configuration.",
            "recommendation": "Revoke the leaked token immediately and retrieve credentials from environment variables.",
            "relative_path": "src/main.py",
            "location": "Line 14",
            "evidence": f"TOKEN = '{dummy_token}'",
            "confidence": 1.0,
            "fingerprint": f"{proj_id}:security:gh_token",
            "status": "open",
        },
        {
            "id": "finding-qual-2",
            "project_id": proj_id,
            "category": FindingCategory.QUALITY.value,
            "severity": FindingSeverity.HIGH.value,
            "priority_tier": PriorityTier.SHOULD_FIX.value,
            "title": "Unbounded Database Connection Pool",
            "description": "Database connection pool has no maximum size configured, leading to potential exhaustion under load.",
            "recommendation": "Configure pool_size=10 and max_overflow=20 in database session factory.",
            "relative_path": "src/main.py",
            "location": "Line 32",
            "evidence": "engine = create_engine(DATABASE_URL)",
            "confidence": 0.95,
            "fingerprint": f"{proj_id}:quality:db_pool",
            "status": "open",
        },
    ])

    return repo, proj_id


def test_assistant_seven_questions_produce_distinct_answers(populated_project):
    """
    Validates that the 7 core question types produce completely distinct,
    evidence-grounded, non-repetitive answers in Local mode.
    """
    repo, proj_id = populated_project
    pipeline = RAGPipeline(repo=repo)

    questions = [
        ("Explain my project", ["Overview", "Purpose", "Ecosystem", "OrderService"]),
        ("What should I fix first?", ["Priority", "Roadmap", "Fix First", "Hardcoded GitHub Personal Token"]),
        ("Are there security problems?", ["Security Findings", "Critical", "Token", "src/main.py"]),
        ("How good are my tests?", ["Testing Health", "tests/test_orders.py", "pytest"]),
        ("Explain my project structure", ["Project Structure", "Directory Layout", "src/", "tests/"]),
        ("What libraries does this project use?", ["Dependencies & Libraries", "fastapi", "uvicorn", "pydantic"]),
        ("Are there duplicate files?", ["Duplicate Files Analysis", "deadbeefcafe", "logo.png", "20.0 KB"]),
    ]

    answers = []
    for q_text, expected_terms in questions:
        res = pipeline.query(project_id=proj_id, message=q_text, search_mode=SearchMode.HYBRID)
        assert res.provider == "local"
        ans = res.answer
        assert len(ans) > 80, f"Answer for '{q_text}' was unexpectedly short: {ans}"

        # Check required grounded terms
        for term in expected_terms:
            assert term.lower() in ans.lower(), f"Expected term '{term}' not found in answer for '{q_text}':\n{ans}"

        answers.append((q_text, ans))

    # Verify that all 7 answers are substantially distinct from each other (no copy-pasted canned templates)
    for i in range(len(answers)):
        for j in range(i + 1, len(answers)):
            q1, a1 = answers[i]
            q2, a2 = answers[j]
            assert a1 != a2, f"Answers for '{q1}' and '{q2}' are identical!"

            # Verify headings are different
            a1_title = a1.splitlines()[0] if a1.splitlines() else ""
            a2_title = a2.splitlines()[0] if a2.splitlines() else ""
            assert a1_title != a2_title, f"Headings for '{q1}' and '{q2}' are identical: {a1_title}"


def test_assistant_conversational_follow_ups(populated_project):
    """
    Validates that natural follow-up questions ('Why?', 'What about the second one?')
    maintain conversational context rather than resetting to a generic answer.
    """
    repo, proj_id = populated_project
    pipeline = RAGPipeline(repo=repo)

    conv_id = "test-conversation-session-42"

    # Turn 1: Ask priority question
    r1 = pipeline.query(
        project_id=proj_id,
        message="What should I fix first?",
        conversation_id=conv_id,
    )
    assert "Hardcoded GitHub Personal Token" in r1.answer
    assert "Unbounded Database Connection Pool" in r1.answer

    # Turn 2: Follow up with "Why?"
    r2 = pipeline.query(
        project_id=proj_id,
        message="Why?",
        conversation_id=conv_id,
    )
    # Should explain why the top priority finding matters
    assert "Why This Matters" in r2.answer
    assert "Hardcoded GitHub Personal Token" in r2.answer
    assert "Risk" in r2.answer or "Impact" in r2.answer

    # Turn 3: Follow up with "What about the second one?"
    r3 = pipeline.query(
        project_id=proj_id,
        message="What about the second one?",
        conversation_id=conv_id,
    )
    # Should explain finding #2 (Unbounded Database Connection Pool)
    assert "Unbounded Database Connection Pool" in r3.answer
    assert "Quality" in r3.answer or "HIGH" in r3.answer
    assert "How to Fix" in r3.answer or "What Was Detected" in r3.answer


def test_assistant_clean_project_honesty(tmp_path: Path):
    """
    Verifies that when a project has NO security issues, NO duplicates, and NO tests,
    the assistant honestly states the absence of data rather than inventing or failing.
    """
    db_path = tmp_path / "clean_project.db"
    db = get_db(str(db_path))
    repo = Repository(db)

    clean_dir = tmp_path / "clean_repo"
    clean_dir.mkdir()
    (clean_dir / "index.js").write_text("console.log('clean');", encoding="utf-8")

    proj = repo.create_project(name="CleanJS", root_path=str(clean_dir))
    proj_id = proj["id"]

    f = repo.upsert_file(
        project_id=proj_id,
        path=str(clean_dir / "index.js"),
        relative_path="index.js",
        filename="index.js",
        extension=".js",
        category="source",
        size_bytes=24,
        modified_time="2026-10-07T10:00:00",
        sha256="abcdef123456",
    )
    repo.upsert_extraction(
        file_id=f["id"],
        project_id=proj_id,
        content_text="console.log('clean');",
        char_count=21,
        status="completed",
    )

    pipeline = RAGPipeline(repo=repo)

    # 1. Security on clean project
    sec_res = pipeline.query(project_id=proj_id, message="Are there security problems?")
    assert "No security vulnerabilities or secret leaks were detected" in sec_res.answer

    # 2. Tests on project with no tests
    test_res = pipeline.query(project_id=proj_id, message="How good are my tests?")
    assert "I couldn't find tests in this project" in test_res.answer
    assert "0 test files detected" in test_res.answer

    # 3. Duplicates on clean project
    dup_res = pipeline.query(project_id=proj_id, message="Are there duplicate files?")
    assert "No duplicate files were detected" in dup_res.answer

    # 4. Dependencies on project without manifests
    dep_res = pipeline.query(project_id=proj_id, message="What libraries does this project use?")
    assert "No package manifests were found in this project" in dep_res.answer

    # 5. Fix first on clean project
    fix_res = pipeline.query(project_id=proj_id, message="What should I fix first?")
    assert "No urgent problems were detected" in fix_res.answer


def test_assistant_zero_secret_leak(populated_project):
    """
    Verifies that raw secret tokens are never leaked in assistant answers.
    """
    repo, proj_id = populated_project
    pipeline = RAGPipeline(repo=repo)

    res = pipeline.query(
        project_id=proj_id,
        message="What is the exact secret token in main.py?",
    )
    raw_token_pattern = "gh" + "p_"
    # The raw token should be redacted
    assert "[REDACTED:GITHUB_TOKEN]" in res.answer or "[REDACTED" in res.answer
    # The actual 36-char raw token body should never appear intact
    assert "111122223333444455556666777788889999" not in res.answer
