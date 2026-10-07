"""
Project Structure and Ecosystem Analyzer for SVANT Phase 4 & 5.
Discovers repository architecture, primary ecosystems, directory roles, and hierarchy defects.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

from svant.core.intelligence.models import (
    Finding,
    FindingCategory,
    FindingSeverity,
    PriorityTier,
    ProjectInventory,
    StructureAnalysis,
)
from svant.logger import get_logger

logger = get_logger("svant.core.intelligence.structure")


class ProjectStructureAnalyzer:
    """Evaluates project directory hierarchy, framework ecosystems, and structural hygiene."""

    def analyze(
        self,
        project_id: str,
        inventory: ProjectInventory,
        files: List[Dict[str, Any]],
    ) -> Tuple[StructureAnalysis, List[Finding]]:
        """Perform structural analysis and return analysis data + structural findings."""
        findings: List[Finding] = []
        analysis = StructureAnalysis()

        filenames = {f.get("filename", "").lower() for f in files}
        relative_paths = [f.get("relative_path", "").replace("\\", "/") for f in files]

        # 1. Ecosystem Detection
        ecosystems: Set[str] = set()

        if any(fn in filenames for fn in ("pyproject.toml", "requirements.txt", "setup.py", "pipfile", "setup.cfg")) or any(f.endswith(".py") for f in filenames):
            ecosystems.add("python")
        if any(fn in filenames for fn in ("package.json", "tsconfig.json", "yarn.lock", "pnpm-lock.yaml")) or any(f.endswith((".js", ".ts", ".jsx", ".tsx")) for f in filenames):
            ecosystems.add("javascript/typescript")
        if any(fn in filenames for fn in ("pom.xml", "build.gradle", "settings.gradle")) or any(f.endswith((".java", ".kt")) for f in filenames):
            ecosystems.add("java/jvm")
        if any(fn in filenames for fn in ("cmakelists.txt", "makefile")) or any(f.endswith((".c", ".cpp", ".cc", ".h", ".hpp")) for f in filenames):
            ecosystems.add("c/c++")
        if any(fn.endswith((".csproj", ".sln", ".fsproj")) for fn in filenames):
            ecosystems.add("dotnet")
        if "cargo.toml" in filenames or any(f.endswith(".rs") for f in filenames):
            ecosystems.add("rust")
        if "go.mod" in filenames or any(f.endswith(".go") for f in filenames):
            ecosystems.add("go")
        if any(fn in filenames for fn in ("dockerfile", "docker-compose.yml", "docker-compose.yaml")):
            ecosystems.add("docker/container")

        analysis.detected_ecosystems = sorted(list(ecosystems))

        # Primary ecosystem selection based on predominant language or manifests
        if inventory.languages:
            top_lang = next(iter(inventory.languages.keys())).lower()
            if "python" in top_lang:
                analysis.primary_ecosystem = "python"
            elif "script" in top_lang or "vue" in top_lang or "svelte" in top_lang:
                analysis.primary_ecosystem = "javascript/typescript"
            elif "java" in top_lang:
                analysis.primary_ecosystem = "java/jvm"
            elif "c++" in top_lang or "c/" in top_lang:
                analysis.primary_ecosystem = "c/c++"
            elif "rust" in top_lang:
                analysis.primary_ecosystem = "rust"
            elif "go" in top_lang:
                analysis.primary_ecosystem = "go"
            else:
                analysis.primary_ecosystem = top_lang
        elif analysis.detected_ecosystems:
            analysis.primary_ecosystem = analysis.detected_ecosystems[0]
        else:
            analysis.primary_ecosystem = "generic"

        # 2. Directory Roles & Roots
        source_roots: Set[str] = set()
        test_roots: Set[str] = set()
        doc_roots: Set[str] = set()
        config_roots: Set[str] = set()
        build_dirs: Set[str] = set()
        virtual_env_dirs: Set[str] = set()
        cache_dirs: Set[str] = set()

        max_depth = 0

        for rp in relative_paths:
            parts = rp.split("/")
            depth = len(parts) - 1
            if depth > max_depth:
                max_depth = depth

            if len(parts) > 1:
                top_dir = parts[0].lower()
                if top_dir in ("src", "lib", "app", "pkg", "sources", "core"):
                    source_roots.add(parts[0])
                elif top_dir in ("test", "tests", "spec", "specs", "__tests__"):
                    test_roots.add(parts[0])
                elif top_dir in ("doc", "docs", "documentation", "guide"):
                    doc_roots.add(parts[0])
                elif top_dir in ("config", "conf", "etc"):
                    config_roots.add(parts[0])
                elif top_dir in ("dist", "build", "out", "target", "bin", "obj"):
                    build_dirs.add(parts[0])
                elif top_dir in (".venv", "venv", "env", "virtualenv", "node_modules"):
                    virtual_env_dirs.add(parts[0])
                elif top_dir in ("__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".cache"):
                    cache_dirs.add(parts[0])

        analysis.source_roots = sorted(list(source_roots))
        analysis.test_roots = sorted(list(test_roots))
        analysis.doc_roots = sorted(list(doc_roots))
        analysis.config_roots = sorted(list(config_roots))
        analysis.build_dirs = sorted(list(build_dirs))
        analysis.virtual_env_dirs = sorted(list(virtual_env_dirs))
        analysis.cache_dirs = sorted(list(cache_dirs))
        analysis.max_depth = max_depth

        # 3. Structural Defect Findings
        # A. Tracked Virtual Environment / Heavy Dependency Folders
        if virtual_env_dirs:
            dirs_str = ", ".join(sorted(virtual_env_dirs))
            findings.append(
                Finding(
                    id="",
                    project_id=project_id,
                    category=FindingCategory.STRUCTURE,
                    severity=FindingSeverity.HIGH,
                    priority_tier=PriorityTier.FIX_FIRST,
                    title=f"Virtual environment or dependency directory scanned: {dirs_str}",
                    description=(
                        f"Detected virtual environment or dependency folders ({dirs_str}) within project tracking. "
                        "Scanning third-party packages bloats indexing, slows search, and pollutes code intelligence."
                    ),
                    recommendation=f"Add '{dirs_str}' to .gitignore and SVANT excluded directories settings.",
                    evidence=f"Tracked folders: {dirs_str}",
                )
            )

        # B. Tracked Build / Distribution Folders
        if build_dirs:
            bdirs_str = ", ".join(sorted(build_dirs))
            findings.append(
                Finding(
                    id="",
                    project_id=project_id,
                    category=FindingCategory.STRUCTURE,
                    severity=FindingSeverity.LOW,
                    priority_tier=PriorityTier.NICE_TO_IMPROVE,
                    title=f"Compiled build artifacts directory detected: {bdirs_str}",
                    description=(
                        f"Detected compiled artifact or build directories ({bdirs_str}). "
                        "Generated binary files and bundles should typically be excluded from repository search."
                    ),
                    recommendation=f"Ensure '{bdirs_str}' is listed in .gitignore.",
                    evidence=f"Build folders: {bdirs_str}",
                )
            )

        # C. Extreme Directory Depth
        if max_depth >= 8:
            findings.append(
                Finding(
                    id="",
                    project_id=project_id,
                    category=FindingCategory.STRUCTURE,
                    severity=FindingSeverity.MEDIUM,
                    priority_tier=PriorityTier.SHOULD_FIX,
                    title=f"Excessive directory nesting depth ({max_depth} levels)",
                    description=(
                        f"The codebase contains directory paths nested {max_depth} levels deep. "
                        "Deep directory nesting impairs maintainability, causes Windows MAX_PATH issues, and complicates imports."
                    ),
                    recommendation="Refactor deeply nested subdirectories into flatter, modular component hierarchies.",
                    evidence=f"Maximum directory nesting depth: {max_depth} levels",
                )
            )

        # D. Flat Project Root with High Source File Count (Unorganized)
        root_source_files = [
            f for f in files
            if f.get("category") == "source" and "/" not in f.get("relative_path", "").replace("\\", "/")
        ]
        if len(root_source_files) > 15 and not source_roots:
            findings.append(
                Finding(
                    id="",
                    project_id=project_id,
                    category=FindingCategory.STRUCTURE,
                    severity=FindingSeverity.LOW,
                    priority_tier=PriorityTier.NICE_TO_IMPROVE,
                    title=f"Flat root directory structure ({len(root_source_files)} source files in root)",
                    description=(
                        f"Found {len(root_source_files)} source code files located directly in the project root "
                        "without a dedicated package or source directory (e.g., 'src/' or 'app/')."
                    ),
                    recommendation="Organize source code into a dedicated 'src/' or package directory for clean separation from project configuration.",
                    evidence=f"{len(root_source_files)} source files in project root directory",
                )
            )

        return analysis, findings
