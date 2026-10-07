"""
Dependency Intelligence Analyzer for SVANT Phase 4 & 5.
Parses manifests, verifies lockfiles, inspects version pinning, and identifies dependency declaration inconsistencies.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Set, Tuple

from svant.core.intelligence.models import (
    Finding,
    FindingCategory,
    FindingSeverity,
    PriorityTier,
)
from svant.db.repository import Repository
from svant.logger import get_logger

logger = get_logger("svant.core.intelligence.dependencies")


class DependencyAnalyzer:
    """Analyzes package manifests, dependency declarations, and lockfile synchronization."""

    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    def analyze(self, project_id: str, files: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], List[Finding]]:
        """
        Evaluate project dependencies across Python, Node, and other ecosystems.
        Returns dependency summary dictionary and list of findings.
        """
        findings: List[Finding] = []
        filenames = {f.get("filename", "").lower(): f for f in files}

        manifest_count = 0
        direct_dep_count = 0
        detected_manifests: List[str] = []
        lockfiles_present: List[str] = []

        # 1. Node.js (package.json + lockfiles)
        if "package.json" in filenames:
            pkg_file = filenames["package.json"]
            manifest_count += 1
            detected_manifests.append("package.json")

            has_lock = any(
                lk in filenames for lk in ("package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb")
            )
            if has_lock:
                for lk in ("package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb"):
                    if lk in filenames:
                        lockfiles_present.append(lk)
            else:
                findings.append(
                    Finding(
                        id="",
                        project_id=project_id,
                        category=FindingCategory.DEPENDENCIES,
                        severity=FindingSeverity.MEDIUM,
                        priority_tier=PriorityTier.SHOULD_FIX,
                        title="Missing lockfile for package.json",
                        description=(
                            "Found 'package.json' without a corresponding lockfile (package-lock.json, yarn.lock, or pnpm-lock.yaml). "
                            "Unpinned builds risk non-deterministic installs and production breakage from breaking upstream updates."
                        ),
                        recommendation="Run 'npm install' or 'yarn' and commit the generated lockfile to version control.",
                        file_id=pkg_file["id"],
                        relative_path=pkg_file.get("relative_path"),
                        location="File level",
                        evidence="package.json found without lockfile",
                    )
                )

            # Parse package.json dependencies
            ext_rec = self.repo.get_extraction(pkg_file["id"])
            if ext_rec and ext_rec.get("content_text"):
                try:
                    data = json.loads(ext_rec["content_text"])
                    deps = data.get("dependencies", {})
                    dev_deps = data.get("devDependencies", {})
                    total_pkg_deps = len(deps) + len(dev_deps)
                    direct_dep_count += total_pkg_deps

                    if len(deps) > 60:
                        findings.append(
                            Finding(
                                id="",
                                project_id=project_id,
                                category=FindingCategory.DEPENDENCIES,
                                severity=FindingSeverity.LOW,
                                priority_tier=PriorityTier.NICE_TO_IMPROVE,
                                title=f"High dependency count in package.json ({len(deps)} direct dependencies)",
                                description=f"package.json declares {len(deps)} direct production dependencies, which increases supply-chain surface area.",
                                recommendation="Audit dependencies and prune unneeded packages or move tooling to devDependencies.",
                                file_id=pkg_file["id"],
                                relative_path=pkg_file.get("relative_path"),
                                evidence=f"Direct dependencies: {len(deps)}, Dev dependencies: {len(dev_deps)}",
                            )
                        )
                except Exception as e:
                    logger.debug(f"Failed to parse package.json content: {e}")

        # 2. Python (requirements.txt / pyproject.toml / Pipfile)
        if "requirements.txt" in filenames:
            req_file = filenames["requirements.txt"]
            manifest_count += 1
            detected_manifests.append("requirements.txt")

            ext_rec = self.repo.get_extraction(req_file["id"])
            if ext_rec and ext_rec.get("content_text"):
                lines = [l.strip() for l in ext_rec["content_text"].splitlines() if l.strip() and not l.strip().startswith("#")]
                direct_dep_count += len(lines)

                # Check for unpinned dependencies (e.g., 'requests' without == or >=)
                unpinned: List[str] = []
                duplicates: Set[str] = set()
                seen_pkgs: Set[str] = set()

                for line in lines:
                    pkg_name = re.split(r"[=><~]", line)[0].strip().lower()
                    if pkg_name:
                        if pkg_name in seen_pkgs:
                            duplicates.add(pkg_name)
                        seen_pkgs.add(pkg_name)

                    if line and not any(op in line for op in ("==", ">=", "<=", "~=", ">", "<")):
                        unpinned.append(line)

                if unpinned:
                    sample = ", ".join(unpinned[:5])
                    findings.append(
                        Finding(
                            id="",
                            project_id=project_id,
                            category=FindingCategory.DEPENDENCIES,
                            severity=FindingSeverity.LOW,
                            priority_tier=PriorityTier.SHOULD_FIX,
                            title=f"Unpinned package versions in requirements.txt ({len(unpinned)} packages)",
                            description=(
                                f"Found {len(unpinned)} package dependencies without version pins in requirements.txt (e.g., {sample}). "
                                "Unpinned dependencies allow unexpected breaking updates to be installed."
                            ),
                            recommendation="Pin dependencies to compatible versions using '==' or '~=' (e.g. package==1.2.3).",
                            file_id=req_file["id"],
                            relative_path=req_file.get("relative_path"),
                            location=f"{len(unpinned)} unpinned entries",
                            evidence=f"Unpinned packages: {sample}",
                        )
                    )

                if duplicates:
                    dup_sample = ", ".join(list(duplicates)[:4])
                    findings.append(
                        Finding(
                            id="",
                            project_id=project_id,
                            category=FindingCategory.DEPENDENCIES,
                            severity=FindingSeverity.LOW,
                            priority_tier=PriorityTier.NICE_TO_IMPROVE,
                            title=f"Duplicate package declarations in requirements.txt ({len(duplicates)} packages)",
                            description=f"Duplicate declarations detected for: {dup_sample}.",
                            recommendation="Consolidate duplicate package declarations into single requirements entries.",
                            file_id=req_file["id"],
                            relative_path=req_file.get("relative_path"),
                            evidence=f"Duplicates: {dup_sample}",
                        )
                    )

        if "pyproject.toml" in filenames:
            manifest_count += 1
            detected_manifests.append("pyproject.toml")
            if "poetry.lock" in filenames:
                lockfiles_present.append("poetry.lock")

        summary = {
            "manifest_count": manifest_count,
            "direct_dependencies_count": direct_dep_count,
            "manifests": detected_manifests,
            "lockfiles": lockfiles_present,
            "vulnerability_verification": "unavailable_local_offline",
            "vulnerability_note": "Local heuristic check only. External vulnerability database lookup is currently offline.",
        }

        return summary, findings
