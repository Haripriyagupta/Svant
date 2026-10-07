"""
Project Hygiene & Cleanup Analyzer for SVANT Phase 4 & 5.
Identifies duplicate files, oversized assets, stale source files, and temporary clutter.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Tuple

from svant.core.intelligence.models import (
    Finding,
    FindingCategory,
    FindingSeverity,
    PriorityTier,
    ProjectInventory,
)
from svant.db.repository import Repository
from svant.logger import get_logger

logger = get_logger("svant.core.intelligence.hygiene")

# File patterns indicating accidental temporary or system clutter
TEMP_FILENAMES = {
    ".ds_store", "thumbs.db", "desktop.ini", ".directory", "npm-debug.log",
    "yarn-debug.log", "yarn-error.log", ".eslintcache",
}

TEMP_EXTENSIONS = {
    ".tmp", ".bak", ".swp", ".swo", "~", ".log",
}


class HygieneAnalyzer:
    """Analyzes codebase hygiene: duplicate files, clutter, stale files, and bloating."""

    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    def analyze(
        self,
        project_id: str,
        inventory: ProjectInventory,
        files: List[Dict[str, Any]],
    ) -> Tuple[Dict[str, Any], List[Finding]]:
        """Evaluate repository hygiene and return metrics + findings."""
        findings: List[Finding] = []

        # 1. Exact Duplicate Files Analysis (via repository SHA-256 clusters)
        duplicate_clusters = self.repo.get_duplicate_files(project_id)
        total_dup_files = sum(c["file_count"] for c in duplicate_clusters)
        total_wasted_bytes = sum(c["wasted_bytes"] for c in duplicate_clusters)

        if duplicate_clusters:
            sample_dups = duplicate_clusters[0]
            first_cluster_paths = [f["relative_path"] for f in sample_dups["files"][:3]]
            paths_sample = ", ".join(first_cluster_paths)
            wasted_mb = total_wasted_bytes / (1024 * 1024)

            findings.append(
                Finding(
                    id="",
                    project_id=project_id,
                    category=FindingCategory.HYGIENE,
                    severity=FindingSeverity.MEDIUM if wasted_mb > 5.0 else FindingSeverity.LOW,
                    priority_tier=PriorityTier.SHOULD_FIX,
                    title=f"Duplicate files detected ({len(duplicate_clusters)} identical content groups)",
                    description=(
                        f"Found {total_dup_files} files across {len(duplicate_clusters)} duplicate groups, "
                        f"wasting approximately {wasted_mb:.2f} MB of local storage. "
                        f"Example duplicate files: {paths_sample}."
                    ),
                    recommendation="Review duplicate files in the Duplicates tab and remove redundant copies.",
                    location="Project-wide",
                    evidence=f"{total_dup_files} duplicates across {len(duplicate_clusters)} clusters ({wasted_mb:.2f} MB)",
                )
            )

        # 2. Oversized Files (> 10MB or > 25MB)
        large_files = [f for f in files if f.get("size_bytes", 0) > 10 * 1024 * 1024]
        for lf in large_files[:5]:
            mb = lf["size_bytes"] / (1024 * 1024)
            findings.append(
                Finding(
                    id="",
                    project_id=project_id,
                    category=FindingCategory.HYGIENE,
                    severity=FindingSeverity.LOW if mb < 25.0 else FindingSeverity.MEDIUM,
                    priority_tier=PriorityTier.NICE_TO_IMPROVE,
                    title=f"Oversized file stored in repository ({mb:.1f} MB): {lf['filename']}",
                    description=(
                        f"File '{lf['relative_path']}' is {mb:.1f} MB. Large binary or data files in Git repositories "
                        "drastically increase repository clone times and disk consumption."
                    ),
                    recommendation="Consider using Git LFS, cloud storage, or external asset hosting for large files.",
                    file_id=lf["id"],
                    relative_path=lf.get("relative_path"),
                    location="File level",
                    evidence=f"File size: {mb:.1f} MB",
                )
            )

        # 3. Temporary / OS / Editor Clutter Files
        clutter_files: List[Dict[str, Any]] = []
        for f in files:
            name_lower = f.get("filename", "").lower()
            ext = f.get("extension", "").lower()
            if name_lower in TEMP_FILENAMES or ext in TEMP_EXTENSIONS or name_lower.endswith("~"):
                clutter_files.append(f)

        if clutter_files:
            sample_clutter = ", ".join([f["filename"] for f in clutter_files[:4]])
            findings.append(
                Finding(
                    id="",
                    project_id=project_id,
                    category=FindingCategory.HYGIENE,
                    severity=FindingSeverity.LOW,
                    priority_tier=PriorityTier.NICE_TO_IMPROVE,
                    title=f"Temporary, editor, or OS clutter files detected ({len(clutter_files)} files)",
                    description=(
                        f"Found {len(clutter_files)} temporary or system files (e.g., {sample_clutter}). "
                        "These files add noise and should be excluded via .gitignore."
                    ),
                    recommendation="Remove temporary files and add their patterns to your root .gitignore.",
                    location="Multiple locations",
                    evidence=f"Clutter files found: {sample_clutter}",
                )
            )

        # 4. Stale Files (Unmodified for > 365 days in active repository)
        now = datetime.datetime.now(datetime.timezone.utc)
        stale_files: List[Dict[str, Any]] = []
        for f in files:
            mtime_str = f.get("modified_time")
            if mtime_str:
                try:
                    # Clean trailing Z for fromisoformat
                    clean_iso = mtime_str.replace("Z", "+00:00")
                    mtime = datetime.datetime.fromisoformat(clean_iso)
                    if (now - mtime).days > 365:
                        stale_files.append(f)
                except Exception:
                    pass

        # If project has over 10 files and > 60% are stale, report as informational/low
        if len(files) >= 15 and len(stale_files) > (len(files) * 0.6):
            findings.append(
                Finding(
                    id="",
                    project_id=project_id,
                    category=FindingCategory.HYGIENE,
                    severity=FindingSeverity.INFO,
                    priority_tier=PriorityTier.INFORMATIONAL,
                    title=f"High proportion of stale files ({len(stale_files)} files unmodified for over 1 year)",
                    description=f"{len(stale_files)} files have not been modified in over a year. The repository may contain obsolete modules or archived assets.",
                    recommendation="Audit stale files for deprecation or archival.",
                    location="Project-wide",
                    evidence=f"{len(stale_files)} of {len(files)} files unmodified for > 365 days",
                )
            )

        summary = {
            "duplicate_groups_count": len(duplicate_clusters),
            "duplicate_files_count": total_dup_files,
            "wasted_bytes": total_wasted_bytes,
            "oversized_files_count": len(large_files),
            "clutter_files_count": len(clutter_files),
            "stale_files_count": len(stale_files),
        }

        return summary, findings
