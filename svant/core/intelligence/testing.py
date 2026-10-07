"""
Testing Intelligence Analyzer for SVANT Phase 4 & 5.
Evaluates test suites, test-to-code ratios, test configurations, and testing coverage gaps.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from svant.core.intelligence.models import (
    Finding,
    FindingCategory,
    FindingSeverity,
    PriorityTier,
    ProjectInventory,
    StructureAnalysis,
)
from svant.logger import get_logger

logger = get_logger("svant.core.intelligence.testing")


class TestingAnalyzer:
    """Evaluates test suite presence, structure, and test-to-source ratios."""

    def analyze(
        self,
        project_id: str,
        inventory: ProjectInventory,
        structure: StructureAnalysis,
        files: List[Dict[str, Any]],
    ) -> Tuple[Dict[str, Any], List[Finding]]:
        """Evaluate testing health and return metrics + findings."""
        findings: List[Finding] = []

        test_files = inventory.test_files
        source_count = inventory.source_files
        test_count = len(test_files)

        filenames_lower = {f.get("filename", "").lower() for f in files}

        # Detect test configurations
        test_configs: List[str] = []
        for cfg in ("pytest.ini", "conftest.py", "setup.cfg", "jest.config.js", "jest.config.ts", "vitest.config.ts", ".coveragerc"):
            if cfg in filenames_lower:
                test_configs.append(cfg)

        has_test_roots = bool(structure.test_roots)
        ratio = (test_count / source_count) if source_count > 0 else 0.0

        # Findings Evaluation
        # 1. No tests detected in project with significant source files
        if test_count == 0 and source_count >= 5:
            findings.append(
                Finding(
                    id="",
                    project_id=project_id,
                    category=FindingCategory.TESTING,
                    severity=FindingSeverity.HIGH if source_count >= 20 else FindingSeverity.MEDIUM,
                    priority_tier=PriorityTier.SHOULD_FIX,
                    title="No automated tests detected in codebase",
                    description=(
                        f"Detected {source_count} source code files, but zero automated test files were identified. "
                        "Without unit or integration tests, software regressions cannot be caught automatically during development."
                    ),
                    recommendation="Establish a test suite (e.g. using pytest for Python or Jest for JavaScript) and add unit tests for critical components.",
                    location="Project-wide",
                    evidence=f"0 test files found for {source_count} source files",
                    confidence=1.0,
                )
            )
        # 2. Test directory configured, but zero test files
        elif has_test_roots and test_count == 0:
            findings.append(
                Finding(
                    id="",
                    project_id=project_id,
                    category=FindingCategory.TESTING,
                    severity=FindingSeverity.MEDIUM,
                    priority_tier=PriorityTier.SHOULD_FIX,
                    title=f"Test directory '{structure.test_roots[0]}' is empty",
                    description=f"A dedicated test directory ('{structure.test_roots[0]}') exists, but contains no recognized test files.",
                    recommendation=f"Populate '{structure.test_roots[0]}' with test modules verifying core logic.",
                    location=structure.test_roots[0],
                    evidence=f"Empty test folder: {structure.test_roots[0]}",
                    confidence=0.9,
                )
            )
        # 3. Source-heavy project with disproportionately low test count (ratio < 0.1)
        elif source_count >= 20 and ratio < 0.1:
            findings.append(
                Finding(
                    id="",
                    project_id=project_id,
                    category=FindingCategory.TESTING,
                    severity=FindingSeverity.LOW,
                    priority_tier=PriorityTier.NICE_TO_IMPROVE,
                    title=f"Low test-to-source ratio ({test_count} tests for {source_count} source files)",
                    description=(
                        f"The codebase has {source_count} source files but only {test_count} test files (ratio {ratio:.1%}). "
                        "Expanded automated test coverage improves maintainability and protects against edge-case defects."
                    ),
                    recommendation="Increase test coverage for core business logic, utility modules, and API route handlers.",
                    location="Project-wide",
                    evidence=f"{test_count} test files vs {source_count} source files ({ratio:.1%})",
                    confidence=0.85,
                )
            )

        summary = {
            "test_files_count": test_count,
            "source_files_count": source_count,
            "test_to_source_ratio": round(ratio, 3),
            "test_roots": structure.test_roots,
            "test_configs": test_configs,
        }

        return summary, findings
