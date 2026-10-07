"""
Project Inventory Builder for SVANT Phase 4 & 5.
Analyzes database records for files, categories, extensions, sizes, and indexing states.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from svant.core.intelligence.models import ProjectInventory
from svant.db.repository import Repository
from svant.logger import get_logger

logger = get_logger("svant.core.intelligence.inventory")

# Extension to language map
EXTENSION_LANGUAGE_MAP: Dict[str, str] = {
    ".py": "Python",
    ".pyw": "Python",
    ".js": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".jsx": "JavaScript (React)",
    ".ts": "TypeScript",
    ".tsx": "TypeScript (React)",
    ".html": "HTML",
    ".htm": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".sass": "Sass",
    ".less": "Less",
    ".java": "Java",
    ".c": "C",
    ".h": "C/C++ Header",
    ".cpp": "C++",
    ".cc": "C++",
    ".cxx": "C++",
    ".hpp": "C++ Header",
    ".cs": "C#",
    ".go": "Go",
    ".rs": "Rust",
    ".rb": "Ruby",
    ".php": "PHP",
    ".swift": "Swift",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".scala": "Scala",
    ".sql": "SQL",
    ".sh": "Shell",
    ".bash": "Shell",
    ".zsh": "Shell",
    ".ps1": "PowerShell",
    ".bat": "Batch",
    ".cmd": "Batch",
    ".lua": "Lua",
    ".r": "R",
    ".dart": "Dart",
    ".vue": "Vue",
    ".svelte": "Svelte",
    ".zig": "Zig",
}

MANIFEST_FILENAMES: Set[str] = {
    "package.json",
    "requirements.txt",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "pipfile",
    "pom.xml",
    "build.gradle",
    "settings.gradle",
    "cmakelists.txt",
    "makefile",
    "cargo.toml",
    "go.mod",
}

LOCK_FILENAMES: Set[str] = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "pipfile.lock",
    "cargo.lock",
    "go.sum",
    "composer.lock",
}

DOC_FILENAMES_PREFIXES: Set[str] = {
    "readme", "changelog", "contributing", "license", "authors", "architecture",
    "install", "guide", "faq", "todo", "security", "code_of_conduct",
}

BUILD_DIR_NAMES: Set[str] = {
    "dist", "build", "out", "target", "bin", "obj", "__pycache__", ".next", ".nuxt",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", "coverage", ".coverage",
}


class ProjectInventoryBuilder:
    """Extracts high-level inventory and metrics from tracked project files."""

    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    def build_inventory(self, project_id: str) -> ProjectInventory:
        """Construct full project inventory from authoritative SQLite metadata."""
        project = self.repo.get_project(project_id)
        if not project:
            raise ValueError(f"Project '{project_id}' not found.")

        files = self.repo.list_files(project_id=project_id, limit=100000)
        idx_status = self.repo.get_project_index_status(project_id) or {}

        inventory = ProjectInventory(
            total_files=len(files),
            total_size_bytes=project.get("total_size_bytes", 0),
            chunk_count=idx_status.get("total_chunks", 0),
            vector_count=idx_status.get("total_vectors", 0),
        )

        all_dirs: Set[str] = set()
        category_counts: Dict[str, int] = {}
        ext_counts: Dict[str, int] = {}
        lang_counts: Dict[str, int] = {}

        source_files = 0
        doc_files_count = 0
        config_files = 0
        data_files = 0
        binary_files = 0
        other_files = 0
        unextracted = 0
        indexed = 0

        for f in files:
            cat = f.get("category", "other").lower()
            ext = f.get("extension", "").lower()
            name_lower = f.get("filename", "").lower()
            rel_path = f.get("relative_path", "").replace("\\", "/")

            # Tally categories
            category_counts[cat] = category_counts.get(cat, 0) + 1
            if cat == "source":
                source_files += 1
            elif cat == "document":
                doc_files_count += 1
            elif cat == "config":
                config_files += 1
            elif cat == "data":
                data_files += 1
            elif cat == "binary":
                binary_files += 1
            else:
                other_files += 1

            # Tally extensions
            if ext:
                ext_counts[ext] = ext_counts.get(ext, 0) + 1
            else:
                ext_counts["[none]"] = ext_counts.get("[none]", 0) + 1

            # Tally languages
            if ext in EXTENSION_LANGUAGE_MAP:
                lang = EXTENSION_LANGUAGE_MAP[ext]
                lang_counts[lang] = lang_counts.get(lang, 0) + 1

            # Status tallies
            if f.get("scan_status") in ("unreadable", "failed"):
                unextracted += 1
            if f.get("indexed_status") == "indexed":
                indexed += 1

            # Directory tracking
            parts = rel_path.split("/")
            if len(parts) > 1:
                # Add all parent directories
                for i in range(1, len(parts)):
                    all_dirs.add("/".join(parts[:i]))

            # Categorize special roles
            # 1. Test files
            is_test = (
                "test" in name_lower
                or "spec" in name_lower
                or any(p.lower() in ("test", "tests", "__tests__", "spec", "specs") for p in parts[:-1])
            ) and cat in ("source", "config")
            if is_test:
                inventory.test_files.append({
                    "id": f["id"],
                    "filename": f["filename"],
                    "relative_path": rel_path,
                    "size_bytes": f["size_bytes"],
                })

            # 2. Documentation files
            is_doc = (
                cat == "document"
                or any(name_lower.startswith(prefix) for prefix in DOC_FILENAMES_PREFIXES)
                or any(p.lower() in ("doc", "docs", "documentation") for p in parts[:-1])
            )
            if is_doc:
                inventory.doc_files.append({
                    "id": f["id"],
                    "filename": f["filename"],
                    "relative_path": rel_path,
                    "size_bytes": f["size_bytes"],
                })

            # 3. Dependency manifests & Lockfiles
            if name_lower in MANIFEST_FILENAMES or name_lower.endswith(".csproj") or name_lower.endswith(".sln"):
                inventory.manifest_files.append({
                    "id": f["id"],
                    "filename": f["filename"],
                    "relative_path": rel_path,
                    "size_bytes": f["size_bytes"],
                })
            elif name_lower in LOCK_FILENAMES:
                inventory.lock_files.append({
                    "id": f["id"],
                    "filename": f["filename"],
                    "relative_path": rel_path,
                    "size_bytes": f["size_bytes"],
                })

            # 4. Build artifacts
            if any(p.lower() in BUILD_DIR_NAMES for p in parts[:-1]) or ext in (".pyc", ".o", ".class", ".dll", ".exe", ".so", ".dylib"):
                inventory.build_artifact_files.append({
                    "id": f["id"],
                    "filename": f["filename"],
                    "relative_path": rel_path,
                    "size_bytes": f["size_bytes"],
                })

        # Deep directories (> 6 levels)
        deep_dirs = sorted([d for d in all_dirs if d.count("/") >= 6])

        # Largest files (Top 10)
        sorted_by_size = sorted(files, key=lambda x: x.get("size_bytes", 0), reverse=True)[:10]
        largest = [
            {
                "id": f["id"],
                "filename": f["filename"],
                "relative_path": f["relative_path"],
                "size_bytes": f["size_bytes"],
                "category": f["category"],
            }
            for f in sorted_by_size
        ]

        # Newest & oldest files
        sorted_by_mtime = sorted(
            [f for f in files if f.get("modified_time")],
            key=lambda x: x["modified_time"],
        )
        oldest = [
            {
                "id": f["id"],
                "filename": f["filename"],
                "relative_path": f["relative_path"],
                "modified_time": f["modified_time"],
            }
            for f in sorted_by_mtime[:5]
        ]
        newest = [
            {
                "id": f["id"],
                "filename": f["filename"],
                "relative_path": f["relative_path"],
                "modified_time": f["modified_time"],
            }
            for f in reversed(sorted_by_mtime[-5:])
        ]

        inventory.source_files = source_files
        inventory.document_files = doc_files_count
        inventory.config_files = config_files
        inventory.data_files = data_files
        inventory.binary_files = binary_files
        inventory.other_files = other_files
        inventory.category_counts = category_counts
        inventory.extension_counts = ext_counts
        inventory.languages = dict(sorted(lang_counts.items(), key=lambda item: item[1], reverse=True))
        inventory.largest_files = largest
        inventory.oldest_files = oldest
        inventory.newest_files = newest
        inventory.total_dirs = len(all_dirs)
        inventory.deep_dirs = deep_dirs[:10]
        inventory.unextracted_files = unextracted
        inventory.indexed_files = indexed

        return inventory
