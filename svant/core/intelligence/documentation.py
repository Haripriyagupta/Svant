"""
Documentation Intelligence Analyzer for SVANT Phase 4 & 5.
Evaluates repository documentation, README completeness, setup guides, and missing documentation assets.
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
from svant.db.repository import Repository
from svant.logger import get_logger

logger = get_logger("svant.core.intelligence.documentation")


class DocumentationAnalyzer:
    """Evaluates project documentation presence, depth, and onboarding materials."""

    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    def analyze(
        self,
        project_id: str,
        inventory: ProjectInventory,
        structure: StructureAnalysis,
        files: List[Dict[str, Any]],
    ) -> Tuple[Dict[str, Any], List[Finding]]:
        """Evaluate documentation assets and return metrics + findings."""
        findings: List[Finding] = []

        filenames_map = {f.get("filename", "").lower(): f for f in files}

        # 1. README evaluation
        readme_file = None
        for name in ("readme.md", "readme.txt", "readme.rst", "readme"):
            if name in filenames_map:
                readme_file = filenames_map[name]
                break

        has_readme = readme_file is not None
        readme_char_count = 0
        has_setup_instructions = False

        if readme_file:
            ext_rec = self.repo.get_extraction(readme_file["id"])
            if ext_rec and ext_rec.get("content_text"):
                text = ext_rec["content_text"]
                readme_char_count = len(text)
                text_lower = text.lower()
                has_setup_instructions = any(
                    kw in text_lower for kw in ("install", "setup", "getting started", "run", "usage", "pip install", "npm install")
                )

        # 2. Check for missing README
        if not has_readme and inventory.source_files >= 2:
            findings.append(
                Finding(
                    id="",
                    project_id=project_id,
                    category=FindingCategory.DOCUMENTATION,
                    severity=FindingSeverity.MEDIUM,
                    priority_tier=PriorityTier.SHOULD_FIX,
                    title="Missing README documentation",
                    description=(
                        "No README file (README.md) was found in the project. "
                        "A README provides essential onboarding, architectural overview, and usage instructions for developers."
                    ),
                    recommendation="Create a README.md in the project root detailing the project purpose, architecture, and instructions.",
                    location="Project root",
                    evidence="No README file detected",
                )
            )
        elif has_readme and readme_char_count < 150:
            findings.append(
                Finding(
                    id="",
                    project_id=project_id,
                    category=FindingCategory.DOCUMENTATION,
                    severity=FindingSeverity.LOW,
                    priority_tier=PriorityTier.NICE_TO_IMPROVE,
                    title="README documentation is very brief or incomplete",
                    description=f"The README file contains only {readme_char_count} characters. Detailed setup and architectural explanations are missing.",
                    recommendation="Expand the README with installation steps, dependency setup, and usage examples.",
                    file_id=readme_file["id"],
                    relative_path=readme_file.get("relative_path"),
                    location="File level",
                    evidence=f"README length: {readme_char_count} characters",
                )
            )

        # 3. Setup / Installation Instructions Missing
        if has_readme and readme_char_count >= 150 and not has_setup_instructions and inventory.source_files >= 5:
            findings.append(
                Finding(
                    id="",
                    project_id=project_id,
                    category=FindingCategory.DOCUMENTATION,
                    severity=FindingSeverity.LOW,
                    priority_tier=PriorityTier.NICE_TO_IMPROVE,
                    title="No setup or installation instructions detected in README",
                    description="The README lacks keywords for setup, installation, or execution instructions.",
                    recommendation="Add a 'Getting Started' or 'Installation' section to the README.",
                    file_id=readme_file["id"] if readme_file else None,
                    relative_path=readme_file.get("relative_path") if readme_file else "README.md",
                    evidence="Missing keywords: install, setup, usage, getting started",
                )
            )

        # 4. Environment example file check
        has_env = any(f.get("filename", "").lower().startswith(".env") and not f.get("filename", "").lower().endswith((".example", ".sample", ".template")) for f in files)
        has_env_example = any(f.get("filename", "").lower() in (".env.example", ".env.sample", ".env.template", "env.example") for f in files)

        if has_env and not has_env_example:
            findings.append(
                Finding(
                    id="",
                    project_id=project_id,
                    category=FindingCategory.DOCUMENTATION,
                    severity=FindingSeverity.LOW,
                    priority_tier=PriorityTier.SHOULD_FIX,
                    title="Environment file exists without '.env.example' template",
                    description=(
                        "A local '.env' file is present, but no sanitized '.env.example' template exists. "
                        "Without a template, other contributors cannot determine which environment variables are required."
                    ),
                    recommendation="Commit a '.env.example' file containing the variable names with sanitized/empty values.",
                    location="Project root",
                    evidence="Missing .env.example template",
                )
            )

        # 5. LICENSE check
        has_license = any(f.get("filename", "").lower().startswith("license") for f in files)
        if not has_license and inventory.source_files >= 10:
            findings.append(
                Finding(
                    id="",
                    project_id=project_id,
                    category=FindingCategory.DOCUMENTATION,
                    severity=FindingSeverity.INFO,
                    priority_tier=PriorityTier.INFORMATIONAL,
                    title="No LICENSE file detected",
                    description="The repository does not contain a standard LICENSE file clarifying software usage and distribution rights.",
                    recommendation="Add a LICENSE file (e.g. MIT, Apache-2.0, or proprietary) specifying terms of use.",
                    location="Project root",
                    evidence="No LICENSE file found",
                )
            )

        summary = {
            "has_readme": has_readme,
            "readme_characters": readme_char_count,
            "has_setup_instructions": has_setup_instructions,
            "has_doc_roots": bool(structure.doc_roots),
            "has_license": has_license,
            "has_env_example": has_env_example,
        }

        return summary, findings
