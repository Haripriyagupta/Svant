"""
Code Quality & Maintainability Heuristic Analyzer for SVANT Phase 4 & 5.
Detects oversized source modules, technical debt markers (TODO/FIXME), leftover debug calls, and maintainability risks.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from svant.core.intelligence.models import (
    Finding,
    FindingCategory,
    FindingSeverity,
    PriorityTier,
)
from svant.db.repository import Repository
from svant.logger import get_logger

logger = get_logger("svant.core.intelligence.quality")

# Patterns for tech debt indicators
TODO_PATTERN = re.compile(r"""(?i)\b(?:TODO|FIXME|HACK|XXX|BUG)\b(?::|\s|$)""")

# Patterns for leftover debug statements in source code
DEBUG_PATTERNS = [
    (re.compile(r"""\bconsole\.(?:log|debug|trace)\s*\("""), "JavaScript console.log call", ".js, .ts, .jsx, .tsx"),
    (re.compile(r"""\bdebugger\s*;"""), "JavaScript debugger breakpoint", ".js, .ts, .jsx, .tsx"),
    (re.compile(r"""\bbreakpoint\s*\(\s*\)"""), "Python breakpoint() invocation", ".py"),
    (re.compile(r"""\bimport\s+pdb\b"""), "Python pdb debugger import", ".py"),
    (re.compile(r"""\bvar_dump\s*\("""), "PHP var_dump() statement", ".php"),
]


class QualityAnalyzer:
    """Evaluates code quality heuristics without requiring heavy static analysis compilers."""

    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    def analyze(self, project_id: str, files: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], List[Finding]]:
        """Evaluate source file quality heuristics and return metrics + findings."""
        findings: List[Finding] = []

        total_todos = 0
        total_debug_statements = 0
        large_source_files: List[Dict[str, Any]] = []

        for f in files:
            if f.get("category") != "source":
                continue

            file_id = f["id"]
            filename = f.get("filename", "")
            rel_path = f.get("relative_path", "").replace("\\", "/")
            ext = f.get("extension", "").lower()

            extraction = self.repo.get_extraction(file_id)
            if not extraction or not extraction.get("content_text"):
                continue

            text = extraction["content_text"]
            lines = text.splitlines()
            line_count = len(lines)

            # 1. Extremely Large Source Files (> 1000 lines or > 1500 lines)
            if line_count >= 1000:
                large_source_files.append({"filename": filename, "lines": line_count, "path": rel_path})
                findings.append(
                    Finding(
                        id="",
                        project_id=project_id,
                        category=FindingCategory.MAINTAINABILITY,
                        severity=FindingSeverity.LOW if line_count < 1800 else FindingSeverity.MEDIUM,
                        priority_tier=PriorityTier.SHOULD_FIX if line_count >= 1800 else PriorityTier.NICE_TO_IMPROVE,
                        title=f"Oversized source file ({line_count} lines): {filename}",
                        description=(
                            f"Source file '{rel_path}' contains {line_count} lines of code. "
                            "Monolithic files with high line counts usually violate the Single Responsibility Principle and are harder to test and maintain."
                        ),
                        recommendation="Decompose this large module into smaller, focused helper classes or sub-modules.",
                        file_id=file_id,
                        relative_path=rel_path,
                        location=f"{line_count} lines total",
                        evidence=f"File length: {line_count} lines",
                    )
                )

            # 2. Tech Debt Markers (TODO / FIXME concentration)
            file_todos = 0
            for line_idx, line in enumerate(lines, start=1):
                clean_line = line.strip()
                if TODO_PATTERN.search(clean_line):
                    file_todos += 1
                    total_todos += 1

            if file_todos >= 6:
                findings.append(
                    Finding(
                        id="",
                        project_id=project_id,
                        category=FindingCategory.QUALITY,
                        severity=FindingSeverity.LOW,
                        priority_tier=PriorityTier.NICE_TO_IMPROVE,
                        title=f"High TODO/FIXME comment concentration ({file_todos} markers) in {filename}",
                        description=(
                            f"Found {file_todos} TODO/FIXME markers in '{rel_path}'. "
                            "Accumulated tech debt markers indicate incomplete implementations or deferred fixes."
                        ),
                        recommendation="Address or ticket the outstanding TODO comments.",
                        file_id=file_id,
                        relative_path=rel_path,
                        location=f"{file_todos} markers",
                        evidence=f"{file_todos} TODO/FIXME comments in file",
                    )
                )

            # 3. Leftover Debug Calls (console.log, breakpoint(), etc.)
            for dbg_pattern, dbg_label, dbg_exts in DEBUG_PATTERNS:
                if ext in dbg_exts:
                    for line_idx, line in enumerate(lines, start=1):
                        clean_line = line.strip()
                        # Skip if line is clearly a comment
                        if clean_line.startswith(("//", "#", "/*", "*")):
                            continue
                        if dbg_pattern.search(clean_line):
                            total_debug_statements += 1
                            findings.append(
                                Finding(
                                    id="",
                                    project_id=project_id,
                                    category=FindingCategory.QUALITY,
                                    severity=FindingSeverity.LOW,
                                    priority_tier=PriorityTier.NICE_TO_IMPROVE,
                                    title=f"Potential leftover debug call: {dbg_label} in {filename}",
                                    description=f"Detected '{clean_line[:80]}' on line {line_idx} of '{rel_path}'.",
                                    recommendation="Remove debug statements before releasing or committing code.",
                                    file_id=file_id,
                                    relative_path=rel_path,
                                    location=f"Line {line_idx}",
                                    evidence=f"Line {line_idx}: {clean_line[:80]}",
                                )
                            )
                            break  # Report only once per file per debug pattern

        summary = {
            "total_todo_markers": total_todos,
            "total_debug_statements": total_debug_statements,
            "large_source_files_count": len(large_source_files),
        }

        return summary, findings
