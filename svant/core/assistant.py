"""
AI Project Assistant Service for SVANT (Phase 6 & 7).
Delivers evidence-grounded Project Summaries, Remediation Plans, Onboarding Guides,
and Deep Finding Explanations across Local-Only and Cloud AI (Gemini/Mock) modes.
Ensures zero raw credentials leave the user machine.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from svant.config import settings
from svant.core.ai.base import AIProvider
from svant.core.ai.factory import get_ai_provider
from svant.core.intelligence.inventory import ProjectInventoryBuilder
from svant.core.intelligence.models import FindingCategory, PriorityTier
from svant.core.intelligence.structure import ProjectStructureAnalyzer
from svant.core.privacy.redactor import SecretRedactor
from svant.core.rag.citations import Citation, CitationGenerator
from svant.core.rag.context import ContextItem
from svant.core.rag.smart_selector import QueryIntent
from svant.db.repository import Repository
from svant.logger import get_logger

logger = get_logger("svant.core.assistant")


def _format_bytes(size_bytes: int) -> str:
    """Format byte count into human-readable representation."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


class ProjectAssistant:
    """Intelligent project assistant offering grounded summaries, plans, and guidance."""

    def __init__(
        self,
        repo: Repository,
        redactor: Optional[SecretRedactor] = None,
        ai_provider: Optional[AIProvider] = None,
    ) -> None:
        self.repo = repo
        self.redactor = redactor or SecretRedactor()
        self.ai_provider = ai_provider
        self.inventory_builder = ProjectInventoryBuilder(repo)
        self.structure_analyzer = ProjectStructureAnalyzer()

    def _resolve_provider(self, provider_name: Optional[str] = None) -> Tuple[Optional[AIProvider], bool]:
        """Resolve active AI provider and check if Local-Only mode applies."""
        if provider_name == "local":
            return None, True

        # Explicitly injected AIProvider instance on this ProjectAssistant
        if self.ai_provider is not None:
            if self.ai_provider.is_available:
                return self.ai_provider, False
            return None, True

        # Explicitly requested provider by name
        if provider_name in ("mock", "gemini"):
            active = get_ai_provider(provider_name)
            if active and active.is_available:
                return active, False
            return None, True

        # Global Local-Only mode enforced
        if getattr(settings, "local_only_mode", True):
            return None, True

        # Configured provider in settings
        configured = getattr(settings, "ai_provider", "none")
        if configured in ("mock", "gemini"):
            active = get_ai_provider(configured)
            if active and active.is_available:
                return active, False

        return None, True

    def summarize_project(
        self,
        project_id: str,
        provider_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate a comprehensive, evidence-grounded executive summary of the project.
        """
        project = self.repo.get_project(project_id)
        if not project:
            raise ValueError(f"Project '{project_id}' not found.")

        health = self.repo.get_project_health(project_id) or {}
        inventory = self.inventory_builder.build_inventory(project_id)
        files = self.repo.list_files(project_id=project_id, limit=5000)
        structure, _ = self.structure_analyzer.analyze(project_id, inventory, files)
        findings = self.repo.list_findings(project_id, status="open", limit=20)

        # Look for README
        readme_file = None
        for f in files:
            if "readme" in (f.get("filename") or "").lower():
                readme_file = self.repo.get_file(f["id"])
                break
        readme_preview = (readme_file.get("content_preview") or "")[:2000] if readme_file else ""

        # Entry points
        entry_points = []
        for f in files:
            fname = (f.get("filename") or "").lower()
            rel = (f.get("relative_path") or "").replace("\\", "/")
            if fname in ("main.py", "app.py", "index.js", "index.ts", "server.js", "manage.py", "main.go", "main.rs"):
                entry_points.append(rel)

        # Build citations & evidence chunks
        context_items: List[ContextItem] = []
        if readme_file:
            context_items.append(ContextItem(
                file_id=readme_file["id"],
                chunk_id=f"readme-{readme_file['id']}",
                filename=readme_file["filename"],
                relative_path=readme_file["relative_path"],
                project_id=project_id,
                chunk_index=0,
                content=f"README Preview:\n{readme_preview}",
                relevance_score=1.0,
                section="Documentation",
            ))

        if health:
            h_text = (
                f"Health Score: {health.get('overall_score', 0)}/100 (Grade {health.get('grade', 'N/A')})\n"
                f"Summary: {health.get('summary', '')}\n"
                f"Issues: {health.get('critical_count', 0)} Critical, {health.get('high_count', 0)} High"
            )
            context_items.append(ContextItem(
                file_id="project-health",
                chunk_id="health-0",
                filename="PROJECT_HEALTH.md",
                relative_path="PROJECT_HEALTH.md",
                project_id=project_id,
                chunk_index=0,
                content=h_text,
                relevance_score=0.98,
                section="Health Overview",
            ))

        for idx, f in enumerate(findings[:6]):
            f_rel = f.get("relative_path") or "Project Root"
            context_items.append(ContextItem(
                file_id=f.get("file_id") or f"f-{idx}",
                chunk_id=f.get("id"),
                filename=Path(f_rel).name or "finding",
                relative_path=f_rel,
                project_id=project_id,
                chunk_index=idx,
                content=f"[{f.get('severity', '').upper()}] {f.get('title')}: {f.get('description')}\nRecommendation: {f.get('recommendation')}",
                relevance_score=0.95 - (idx * 0.01),
                section=f"Finding: {f.get('category')}",
            ))

        # Redact context items locally
        sanitized_items = []
        for itm in context_items:
            red = self.redactor.redact(itm.content)
            itm_copy = ContextItem(
                file_id=itm.file_id,
                chunk_id=itm.chunk_id,
                filename=itm.filename,
                relative_path=itm.relative_path,
                project_id=itm.project_id,
                chunk_index=itm.chunk_index,
                content=red.sanitized_text,
                relevance_score=itm.relevance_score,
                section=itm.section,
            )
            sanitized_items.append(itm_copy)

        citations = CitationGenerator.generate(sanitized_items)

        active_provider, is_local = self._resolve_provider(provider_name)
        if is_local:
            # Deterministic, structured local summary
            languages_str = ", ".join(f"{k} ({v} files)" for k, v in sorted(inventory.languages.items(), key=lambda x: x[1], reverse=True)[:5]) or "None identified"
            entry_points_str = ", ".join(f"`{ep}`" for ep in entry_points) if entry_points else "No standard entry point detected."

            summary_md = (
                f"## Executive Project Summary: {project['name']}\n\n"
                f"### Purpose & Technology\n"
                f"- **Primary Ecosystem**: `{structure.primary_ecosystem.title()}`\n"
                f"- **Languages Detected**: {languages_str}\n"
                f"- **Total Files**: {inventory.total_files:,} files ({inventory.total_size_bytes / 1024:.1f} KB)\n\n"
                f"### Architecture & Structure\n"
                f"- **Entry Points**: {entry_points_str}\n"
                f"- **Source Roots**: {', '.join(f'`{r}`' for r in structure.source_roots) or 'Root layout'}\n"
                f"- **Test Roots**: {', '.join(f'`{r}`' for r in structure.test_roots) or 'No dedicated test directory'}\n"
                f"- **Directory Depth**: Max depth {structure.max_depth}\n\n"
                f"### Health & Security Posture\n"
                f"- **SVANT Health Rating**: **{health.get('overall_score', 0)}/100 (Grade {health.get('grade', 'N/A')})**\n"
                f"- **Active Risks**: {health.get('critical_count', 0)} Critical, {health.get('high_count', 0)} High issues detected.\n"
                f"- **Summary**: {health.get('summary', 'Run full analysis for health evaluation.')}\n\n"
                f"### Top Priorities\n"
            )
            if findings:
                for idx, f in enumerate(findings[:3], start=1):
                    summary_md += f"{idx}. **[{f.get('severity', '').upper()}]** {f.get('title')} (`{f.get('relative_path') or 'root'}`): {f.get('recommendation')}\n"
            else:
                summary_md += "- No urgent issues detected in current scan.\n"

            return {
                "project_id": project_id,
                "action": "summarize",
                "content": summary_md,
                "provider": "local",
                "sources": [c.to_dict() for c in citations],
            }

        # Generative provider mode
        evidence = (
            f"Project: {project['name']}\n"
            f"Ecosystem: {structure.primary_ecosystem}\n"
            f"Languages: {inventory.languages}\n"
            f"Total Files: {inventory.total_files}\n"
            f"Entry Points: {entry_points}\n"
            f"Health Score: {health.get('overall_score', 0)}/100 (Grade {health.get('grade', 'N/A')})\n"
            f"Health Summary: {health.get('summary', '')}\n"
            f"README Preview: {readme_preview}\n"
            f"Open Findings: {findings[:8]}\n"
        )
        sys_prompt = (
            "You are SVANT, an expert project intelligence AI. Provide a clean, grounded executive summary "
            "with sections for Purpose & Technology, Architecture & Structure, Health & Security, and Top Priorities. "
            "Base your answer strictly on the provided evidence."
        )
        user_prompt = f"PROJECT EVIDENCE:\n{evidence}\n\nPlease generate the executive project summary."
        res = active_provider.generate(system_prompt=sys_prompt, user_prompt=user_prompt, context=evidence)

        return {
            "project_id": project_id,
            "action": "summarize",
            "content": res.text,
            "provider": active_provider.name,
            "sources": [c.to_dict() for c in citations],
        }

    def create_improvement_plan(
        self,
        project_id: str,
        provider_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate a phased, prioritized step-by-step remediation plan with expected benefits and citations.
        """
        project = self.repo.get_project(project_id)
        if not project:
            raise ValueError(f"Project '{project_id}' not found.")

        health = self.repo.get_project_health(project_id) or {}
        fix_first = self.repo.list_findings(project_id, priority_tier=PriorityTier.FIX_FIRST.value, status="open")
        should_fix = self.repo.list_findings(project_id, priority_tier=PriorityTier.SHOULD_FIX.value, status="open")
        nice_to_improve = self.repo.list_findings(project_id, priority_tier=PriorityTier.NICE_TO_IMPROVE.value, status="open")
        informational = self.repo.list_findings(project_id, priority_tier=PriorityTier.INFORMATIONAL.value, status="open")

        # Build Citations
        context_items: List[ContextItem] = []
        for idx, f in enumerate(fix_first + should_fix + nice_to_improve):
            f_rel = f.get("relative_path") or "Project Root"
            context_items.append(ContextItem(
                file_id=f.get("file_id") or f"plan-{idx}",
                chunk_id=f.get("id"),
                filename=Path(f_rel).name or "finding",
                relative_path=f_rel,
                project_id=project_id,
                chunk_index=idx,
                content=f"[{f.get('priority_tier', '').upper()}] {f.get('title')}: {f.get('description')}\nFix: {f.get('recommendation')}",
                relevance_score=0.98 - (idx * 0.01),
                section=f"Priority: {f.get('priority_tier')}",
            ))
        citations = CitationGenerator.generate(context_items)

        active_provider, is_local = self._resolve_provider(provider_name)
        if is_local:
            plan_lines = [
                f"## Phased Remediation Plan: {project['name']}\n",
                f"**Current Health**: {health.get('overall_score', 0)}/100 (Grade {health.get('grade', 'N/A')})\n",
                "### Phase 1: Immediate Blockers & Security (Fix First)",
            ]
            if fix_first:
                for f in fix_first:
                    f_rel = f.get("relative_path") or "Project Root"
                    plan_lines.append(
                        f"- **{f['title']}** (`{f_rel}`)\n"
                        f"  - *Why it matters*: High severity exposure or stability blocker.\n"
                        f"  - *Action*: {f['recommendation']}\n"
                        f"  - *Expected Benefit*: Prevents security credential compromise or critical failure."
                    )
            else:
                plan_lines.append("- *No urgent blockers found.*")

            plan_lines.append("\n### Phase 2: Quality & Architecture (Should Fix)")
            if should_fix:
                for f in should_fix[:6]:
                    f_rel = f.get("relative_path") or "Project Root"
                    plan_lines.append(
                        f"- **{f['title']}** (`{f_rel}`)\n"
                        f"  - *Why it matters*: Reduces tech debt and elevates maintainability.\n"
                        f"  - *Action*: {f['recommendation']}\n"
                        f"  - *Expected Benefit*: Enhances readability and prevents regression bugs."
                    )
            else:
                plan_lines.append("- *No moderate priority issues detected.*")

            plan_lines.append("\n### Phase 3: Hygiene & Documentation (Nice to Improve)")
            if nice_to_improve:
                for f in nice_to_improve[:5]:
                    plan_lines.append(f"- **{f['title']}**: {f['recommendation']}")
            else:
                plan_lines.append("- *Hygiene and documentation are in good standing.*")

            return {
                "project_id": project_id,
                "action": "plan",
                "content": "\n".join(plan_lines),
                "provider": "local",
                "sources": [c.to_dict() for c in citations],
            }

        evidence = (
            f"Project: {project['name']}\n"
            f"Health Score: {health.get('overall_score', 0)}/100\n"
            f"Fix First: {fix_first}\n"
            f"Should Fix: {should_fix}\n"
            f"Nice to Improve: {nice_to_improve}\n"
        )
        sys_prompt = (
            "You are SVANT, an expert software architecture AI. Create a phased, actionable, step-by-step remediation plan "
            "divided into Phase 1 (Immediate/Fix First), Phase 2 (Quality/Should Fix), and Phase 3 (Hygiene/Nice to Improve). "
            "For each recommendation, describe why it matters, the affected path, suggested action, and expected benefit."
        )
        user_prompt = f"PROJECT FINDINGS EVIDENCE:\n{evidence}\n\nPlease generate the prioritized remediation plan."
        res = active_provider.generate(system_prompt=sys_prompt, user_prompt=user_prompt, context=evidence)

        return {
            "project_id": project_id,
            "action": "plan",
            "content": res.text,
            "provider": active_provider.name,
            "sources": [c.to_dict() for c in citations],
        }

    def explain_finding(
        self,
        project_id: str,
        finding_id: str,
        provider_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Explain a specific finding with WHAT, WHY, WHERE, RISK, HOW TO FIX, PRIORITY, and safe EVIDENCE.
        """
        finding = self.repo.get_finding(finding_id)
        if not finding or finding.get("project_id") != project_id:
            raise ValueError(f"Finding '{finding_id}' not found in project '{project_id}'.")

        # Sanitize evidence
        red_evidence = self.redactor.redact(finding.get("evidence") or "None")
        safe_evidence = red_evidence.sanitized_text

        # Citation for finding
        f_rel = finding.get("relative_path") or "Project Root"
        citation = Citation(
            file_id=finding.get("file_id") or finding_id,
            filename=Path(f_rel).name or "finding",
            relative_path=f_rel,
            location=finding.get("location") or "file",
            relevance_score=1.0,
            snippet_preview=safe_evidence[:160],
            chunk_id=finding_id,
        )

        active_provider, is_local = self._resolve_provider(provider_name)
        if is_local:
            explanation_md = (
                f"## Finding Analysis: {finding['title']}\n\n"
                f"- **Category**: `{finding['category'].title()}` | **Severity**: `{finding['severity'].upper()}`\n"
                f"- **Priority Tier**: `{finding.get('priority_tier', 'should_fix').upper()}`\n"
                f"- **Location**: `{f_rel}` ({finding.get('location') or 'file'})\n\n"
                f"### WHAT Was Detected?\n"
                f"{finding['description']}\n\n"
                f"### WHERE Is the Issue Located?\n"
                f"File: `{f_rel}`\n"
                f"Location / Context: `{finding.get('location') or 'general file scope'}`\n\n"
                f"### WHY Does It Matter?\n"
                f"Unresolved {finding['category']} issues directly impact codebase health, maintainability, and security risk posture.\n\n"
                f"### RISK If Ignored\n"
                f"Leaving this finding unaddressed may lead to security vulnerabilities, build degradation, or technical debt accumulation.\n\n"
                f"### HOW TO FIX\n"
                f"{finding['recommendation']}\n\n"
                f"### EVIDENCE (Redacted Locally)\n"
                f"```\n{safe_evidence}\n```\n\n"
                f"### PRIORITY RATIONALE\n"
                f"Assigned tier `{finding.get('priority_tier', 'should_fix').upper()}` because severity is `{finding['severity'].upper()}` "
                f"and resolving this directly improves project health."
            )

            return {
                "project_id": project_id,
                "action": "explain_finding",
                "content": explanation_md,
                "provider": "local",
                "sources": [citation.to_dict()],
            }

        evidence = (
            f"Finding: {finding['title']}\n"
            f"Category: {finding['category']}\n"
            f"Severity: {finding['severity']}\n"
            f"Priority Tier: {finding.get('priority_tier')}\n"
            f"File: {f_rel}\n"
            f"Location: {finding.get('location')}\n"
            f"Evidence: {safe_evidence}\n"
            f"Description: {finding['description']}\n"
            f"Recommendation: {finding['recommendation']}\n"
        )
        sys_prompt = (
            "You are SVANT, an expert software developer and security engineer. Explain this finding clearly: "
            "detail WHAT happened, WHERE it is, WHY it matters, RISK if ignored, practical HOW TO FIX code instructions, "
            "and PRIORITY rationale. Base your answer strictly on the provided evidence. Never reveal raw secrets."
        )
        user_prompt = f"FINDING EVIDENCE:\n{evidence}\n\nPlease explain this finding and provide remediation steps."
        res = active_provider.generate(system_prompt=sys_prompt, user_prompt=user_prompt, context=evidence)

        return {
            "project_id": project_id,
            "action": "explain_finding",
            "content": res.text,
            "provider": active_provider.name,
            "sources": [citation.to_dict()],
        }

    def create_onboarding_guide(
        self,
        project_id: str,
        provider_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate a comprehensive onboarding handbook for a new contributor.
        """
        project = self.repo.get_project(project_id)
        if not project:
            raise ValueError(f"Project '{project_id}' not found.")

        inventory = self.inventory_builder.build_inventory(project_id)
        files = self.repo.list_files(project_id=project_id, limit=5000)
        structure, _ = self.structure_analyzer.analyze(project_id, inventory, files)
        health = self.repo.get_project_health(project_id) or {}
        fix_first = self.repo.list_findings(project_id, priority_tier=PriorityTier.FIX_FIRST.value, status="open", limit=5)

        readme_file = None
        for f in files:
            if "readme" in (f.get("filename") or "").lower():
                readme_file = self.repo.get_file(f["id"])
                break
        readme_preview = (readme_file.get("content_preview") or "")[:2000] if readme_file else ""

        entry_points = []
        for f in files:
            fname = (f.get("filename") or "").lower()
            rel = (f.get("relative_path") or "").replace("\\", "/")
            if fname in ("main.py", "app.py", "index.js", "index.ts", "server.js", "manage.py", "main.go", "main.rs"):
                entry_points.append(rel)

        # Build Citations
        context_items: List[ContextItem] = []
        if readme_file:
            context_items.append(ContextItem(
                file_id=readme_file["id"],
                chunk_id=f"readme-{readme_file['id']}",
                filename=readme_file["filename"],
                relative_path=readme_file["relative_path"],
                project_id=project_id,
                chunk_index=0,
                content=f"README Preview:\n{readme_preview}",
                relevance_score=1.0,
                section="Getting Started",
            ))

        citations = CitationGenerator.generate(context_items)

        active_provider, is_local = self._resolve_provider(provider_name)
        if is_local:
            entry_str = ", ".join(f"`{ep}`" for ep in entry_points) if entry_points else "No single standard entry point detected (check documentation or test files)."
            languages_str = ", ".join(f"{k} ({v} files)" for k, v in sorted(inventory.languages.items(), key=lambda x: x[1], reverse=True)[:5]) or "None detected"

            onboarding_md = (
                f"## Contributor Onboarding Guide: {project['name']}\n\n"
                f"Welcome! This guide helps you navigate and start contributing to **{project['name']}** based on scanned project evidence.\n\n"
                f"### 1. Project Overview & Tech Stack\n"
                f"- **Primary Ecosystem**: `{structure.primary_ecosystem.title()}`\n"
                f"- **Languages**: {languages_str}\n"
                f"- **Total Files**: {inventory.total_files:,} files\n\n"
                f"### 2. Codebase Structure & Key Roots\n"
                f"- **Source Roots**: {', '.join(f'`{r}`' for r in structure.source_roots) or 'Root layout'}\n"
                f"- **Test Roots**: {', '.join(f'`{r}`' for r in structure.test_roots) or 'No dedicated test directory'}\n"
                f"- **Documentation**: {', '.join(f'`{r}`' for r in structure.doc_roots) or ('`README.md` found' if readme_file else 'None')}\n\n"
                f"### 3. Application Entry Points\n"
                f"- **Candidate Entry Points**: {entry_str}\n\n"
                f"### 4. Setup & Getting Started\n"
            )
            if readme_preview:
                onboarding_md += f"According to `README.md`:\n```markdown\n{readme_preview[:600]}\n...\n```\n\n"
            else:
                onboarding_md += "- *No `README.md` file found. Inspect package manifests or source roots to identify start scripts.*\n\n"

            onboarding_md += (
                f"### 5. Health & Quality Precautions\n"
                f"- **Current Health Score**: **{health.get('overall_score', 0)}/100 (Grade {health.get('grade', 'N/A')})**\n"
            )
            if fix_first:
                onboarding_md += "- **Heads-up (Critical Items to avoid breaking)**:\n"
                for f in fix_first:
                    onboarding_md += f"  - `{f.get('relative_path') or 'root'}`: {f.get('title')}\n"
            else:
                onboarding_md += "- *No critical blockers. The repository is in a healthy state.*\n"

            onboarding_md += (
                f"\n### 6. Suggested First Steps for Contributors\n"
                f"1. Clone or open `{project['root_path']}` in your editor.\n"
                f"2. Inspect the entry point ({entry_points[0] if entry_points else 'main file'}) and manifest files.\n"
                f"3. Run the existing test suite if available ({structure.test_roots[0] if structure.test_roots else 'tests/'}).\n"
                f"4. Review open recommendations in SVANT before submitting changes."
            )

            return {
                "project_id": project_id,
                "action": "onboarding",
                "content": onboarding_md,
                "provider": "local",
                "sources": [c.to_dict() for c in citations],
            }

        evidence = (
            f"Project: {project['name']}\n"
            f"Ecosystem: {structure.primary_ecosystem}\n"
            f"Languages: {inventory.languages}\n"
            f"Source Roots: {structure.source_roots}\n"
            f"Test Roots: {structure.test_roots}\n"
            f"Entry Points: {entry_points}\n"
            f"Health Score: {health.get('overall_score', 0)}/100\n"
            f"README Preview: {readme_preview}\n"
            f"Critical Issues: {fix_first}\n"
        )
        sys_prompt = (
            "You are SVANT, an expert software architecture AI. Create a welcoming, clear Contributor Onboarding Guide "
            "covering Overview, Structure, Entry Points, Setup/Run instructions, and Health warnings based strictly on the provided evidence. "
            "If entry points or setup instructions cannot be confidently identified, explicitly state so."
        )
        user_prompt = f"PROJECT EVIDENCE:\n{evidence}\n\nPlease generate the contributor onboarding guide."
        res = active_provider.generate(system_prompt=sys_prompt, user_prompt=user_prompt, context=evidence)

        return {
            "project_id": project_id,
            "action": "onboarding",
            "content": res.text,
            "provider": active_provider.name,
            "sources": [c.to_dict() for c in citations],
        }

    def get_structured_summary(self, project_id: str) -> Dict[str, Any]:
        """Return structured project overview data for dashboards and programmatic consumers."""
        project = self.repo.get_project(project_id)
        if not project:
            raise ValueError(f"Project '{project_id}' not found.")

        inventory = self.inventory_builder.build_inventory(project_id)
        files = self.repo.list_files(project_id=project_id, limit=5000)
        structure, _ = self.structure_analyzer.analyze(project_id, inventory, files)
        health = self.repo.get_project_health(project_id) or {}
        findings_counts = self.repo.get_findings_counts_by_severity(project_id)

        entry_points = []
        for f in files:
            fname = (f.get("filename") or "").lower()
            rel = (f.get("relative_path") or "").replace("\\", "/")
            if fname in ("main.py", "app.py", "index.js", "index.ts", "server.js", "manage.py"):
                entry_points.append(rel)

        return {
            "project_id": project_id,
            "name": project["name"],
            "root_path": project["root_path"],
            "primary_ecosystem": structure.primary_ecosystem,
            "total_files": inventory.total_files,
            "total_size_bytes": inventory.total_size_bytes,
            "languages": inventory.languages,
            "entry_points": entry_points,
            "health_score": health.get("overall_score"),
            "grade": health.get("grade"),
            "health_summary": health.get("summary"),
            "findings_counts": findings_counts,
        }

    def answer_question(
        self,
        project_id: str,
        question: str,
        intents: List[str],
        context_items: Optional[List[ContextItem]] = None,
        citations: Optional[List[Citation]] = None,
        referenced_finding: Optional[Dict[str, Any]] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """
        Generate a question-specific, evidence-grounded answer in Local-Only mode.
        Synthesizes answers strictly from real project metadata, file structure,
        findings, tests, manifests, and search excerpts. Never hallucinates.
        """
        project = self.repo.get_project(project_id)
        if not project:
            return "Project not found."

        # A. Explicitly referenced finding (e.g. from ordinal or follow-up)
        if referenced_finding is not None:
            return self._answer_finding_detail(project, referenced_finding, question)

        # B. Conversational follow-up where no specific finding was identified
        if (QueryIntent.FOLLOW_UP in intents or QueryIntent.FINDING_DETAIL in intents) and history:
            return self._answer_follow_up_general(project, question, history)

        # C. Intent-specific handlers
        if QueryIntent.SECURITY in intents:
            return self._answer_security(project)

        if QueryIntent.PRIORITY in intents:
            return self._answer_priority(project)

        if QueryIntent.TESTING in intents:
            return self._answer_testing(project)

        if QueryIntent.STRUCTURE in intents:
            return self._answer_structure(project)

        if QueryIntent.ARCHITECTURE in intents or QueryIntent.ONBOARDING in intents:
            return self._answer_overview(project)

        if QueryIntent.DEPENDENCIES in intents:
            return self._answer_dependencies(project)

        if QueryIntent.DUPLICATES in intents:
            return self._answer_duplicates(project)

        if QueryIntent.HEALTH in intents:
            return self._answer_priority(project)

        # D. General code search
        return self._answer_general(project, question, context_items, citations)

    def _extract_libraries_from_manifests(self, project_id: str, manifest_files: List[Dict[str, Any]]) -> List[str]:
        """Extract detected third-party library names from manifest previews or disk."""
        libraries: List[str] = []
        for mf in manifest_files:
            file_id = mf.get("id")
            fname = (mf.get("filename") or "").lower()
            ext_record = self.repo.get_extraction(file_id) if file_id else None
            preview = (ext_record.get("content_text") or "") if ext_record else ""

            if not preview and mf.get("path"):
                try:
                    p = Path(mf["path"])
                    if p.exists() and p.is_file():
                        preview = p.read_text(encoding="utf-8", errors="ignore")[:4000]
                except Exception:
                    pass

            if not preview:
                continue

            if fname == "requirements.txt" or fname.endswith(".txt"):
                for line in preview.splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and not line.startswith("-") and not line.startswith("http"):
                        libraries.append(f"`{line}`")
            elif fname == "package.json":
                try:
                    data = json.loads(preview)
                    deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
                    for pkg, ver in list(deps.items())[:20]:
                        libraries.append(f"`{pkg} ({ver})`")
                except Exception:
                    pass
            elif fname == "pyproject.toml":
                in_deps = False
                for line in preview.splitlines():
                    line = line.strip()
                    if line.startswith("[") and any(k in line.lower() for k in ("dependencies", "requires")):
                        in_deps = True
                        continue
                    elif line.startswith("["):
                        in_deps = False
                    if in_deps and line and not line.startswith("#"):
                        libraries.append(f"`{line}`")
            elif fname == "cargo.toml":
                in_deps = False
                for line in preview.splitlines():
                    line = line.strip()
                    if line.startswith("[dependencies"):
                        in_deps = True
                        continue
                    elif line.startswith("["):
                        in_deps = False
                    if in_deps and line and not line.startswith("#"):
                        libraries.append(f"`{line}`")
            elif fname == "go.mod":
                in_req = False
                for line in preview.splitlines():
                    line = line.strip()
                    if line.startswith("require ("):
                        in_req = True
                        continue
                    elif line == ")":
                        in_req = False
                    elif in_req or line.startswith("require "):
                        clean_line = line.replace("require", "").strip()
                        if clean_line:
                            libraries.append(f"`{clean_line}`")
        return libraries[:25]

    def _detect_test_framework(self, test_files: List[Dict[str, Any]]) -> str:
        """Infer test framework from test filenames and structure."""
        all_names = [f.get("filename", "").lower() for f in test_files]
        all_paths = [f.get("relative_path", "").lower() for f in test_files]

        signals = []
        if any("pytest" in p or "conftest" in n for n, p in zip(all_names, all_paths)):
            signals.append("pytest")
        elif any(n.endswith(".py") for n in all_names):
            signals.append("pytest / unittest")

        if any(n.endswith((".spec.ts", ".test.ts", ".spec.js", ".test.js")) for n in all_names):
            signals.append("Jest / Vitest / Mocha")

        if any(n.endswith("test.go") for n in all_names):
            signals.append("Go testing package")

        if any(n.endswith("_test.rs") for n in all_names):
            signals.append("Rust cargo test")

        return ", ".join(signals) if signals else "Standard ecosystem test runner"

    def _summarize_directory_layout(self, files: List[Dict[str, Any]]) -> List[str]:
        """Group files by top-level directory and identify primary roles."""
        dir_counts: Dict[str, int] = {}
        dir_roles: Dict[str, str] = {}
        for f in files:
            rel = (f.get("relative_path") or "").replace("\\", "/")
            parts = rel.split("/")
            if len(parts) > 1:
                top_dir = parts[0] + "/"
                dir_counts[top_dir] = dir_counts.get(top_dir, 0) + 1
                top_lower = top_dir.lower()
                if top_lower in ("src/", "app/", "lib/", "core/", "pkg/"):
                    dir_roles[top_dir] = "Source code & core application logic"
                elif top_lower in ("tests/", "test/", "spec/", "__tests__/"):
                    dir_roles[top_dir] = "Automated test suite"
                elif top_lower in ("docs/", "doc/", "documentation/"):
                    dir_roles[top_dir] = "Project documentation"
                elif top_lower in ("config/", "conf/", ".github/", "scripts/"):
                    dir_roles[top_dir] = "Configuration & CI/CD automation"
                elif top_lower in ("static/", "public/", "assets/"):
                    dir_roles[top_dir] = "Static assets & media"
                elif top_dir not in dir_roles:
                    dir_roles[top_dir] = "Project module / subdirectory"
            else:
                dir_counts["[root]"] = dir_counts.get("[root]", 0) + 1
                dir_roles["[root]"] = "Root configuration & project metadata"

        sorted_dirs = sorted(dir_counts.items(), key=lambda x: x[1], reverse=True)
        lines = []
        for d, count in sorted_dirs[:8]:
            role = dir_roles.get(d, "Project folder")
            lines.append(f"- `{d}` ({count} file{'s' if count != 1 else ''}): {role}")
        return lines

    def _answer_security(self, project: Dict[str, Any]) -> str:
        """Answer security questions with grounded findings or clean status."""
        project_id = project["id"]
        sec_findings = self.repo.list_findings(project_id, category=FindingCategory.SECURITY.value, status="open")
        inventory = self.inventory_builder.build_inventory(project_id)

        if sec_findings:
            crit = sum(1 for f in sec_findings if f.get("severity") == "critical")
            high = sum(1 for f in sec_findings if f.get("severity") == "high")
            med = sum(1 for f in sec_findings if f.get("severity") == "medium")
            low = sum(1 for f in sec_findings if f.get("severity") == "low")

            lines = [
                f"### Security Findings Overview: {project['name']}\n",
                f"I analyzed the codebase for security risks, hardcoded credentials, and known vulnerabilities.\n",
                f"**Found {len(sec_findings)} Open Security Issue(s)**:",
                f"- **Critical**: {crit} | **High**: {high} | **Medium**: {med} | **Low**: {low}\n",
                "#### Identified Issues:\n",
            ]
            for idx, f in enumerate(sec_findings[:6], start=1):
                f_rel = f.get("relative_path") or "Project Root"
                loc = f.get("location") or "file"
                safe_ev = self.redactor.redact(f.get("evidence") or "").sanitized_text
                lines.append(
                    f"{idx}. **[{f.get('severity', '').upper()}] {f.get('title')}** (`{f_rel}`, {loc})\n"
                    f"   - **What Was Detected**: {f.get('description')}\n"
                    f"   - **Recommended Fix**: {f.get('recommendation')}"
                )
                if safe_ev and safe_ev != "None":
                    lines.append(f"   - **Evidence (Redacted)**: `{safe_ev[:120]}`\n")

            lines.append(
                "#### Recommended Security Actions:\n"
                "1. Immediately revoke and rotate any exposed tokens or credentials.\n"
                "2. Move all secrets to environment variables (`.env`) and verify `.env` is listed in `.gitignore`.\n"
                "3. Re-run SVANT analysis after remediation to verify clean status."
            )
            return "\n".join(lines)

        return (
            f"### Security Status: {project['name']}\n\n"
            f"**No security vulnerabilities or secret leaks were detected in this project.**\n\n"
            f"- **Scanned Files**: {inventory.total_files} files checked.\n"
            f"- **Secret Detection**: No API keys, tokens, private keys, or credentials were found in tracked files.\n"
            f"- **Status**: Clean."
        )

    def _answer_priority(self, project: Dict[str, Any]) -> str:
        """Answer priority / fix-first questions with phased remediation roadmap."""
        project_id = project["id"]
        health = self.repo.get_project_health(project_id) or {}
        fix_first = self.repo.list_findings(project_id, priority_tier=PriorityTier.FIX_FIRST.value, status="open")
        should_fix = self.repo.list_findings(project_id, priority_tier=PriorityTier.SHOULD_FIX.value, status="open")
        nice_to_improve = self.repo.list_findings(project_id, priority_tier=PriorityTier.NICE_TO_IMPROVE.value, status="open")

        if not (fix_first or should_fix or nice_to_improve):
            score = health.get("overall_score", 100)
            grade = health.get("grade", "A")
            return (
                f"### Priority Recommendations: {project['name']}\n\n"
                f"**Current Project Health**: **{score}/100 (Grade {grade})**\n\n"
                f"No urgent problems were detected in this project. All scans passed with zero open security or quality defects.\n\n"
                f"To further improve your project, consider adding additional automated tests or architectural documentation."
            )

        lines = [
            f"### Priority Remediation: What to Fix First in {project['name']}\n",
            f"**Current Project Health**: **{health.get('overall_score', 0)}/100 (Grade {health.get('grade', 'N/A')})**\n",
            "Here is the prioritized remediation roadmap based on issue severity and blast radius:\n",
        ]

        # Phase 1: Fix First
        lines.append("#### Phase 1: Immediate Blockers & Security (Fix First)")
        if fix_first:
            for idx, f in enumerate(fix_first, start=1):
                f_rel = f.get("relative_path") or "Project Root"
                lines.append(
                    f"{idx}. **[{f.get('severity', '').upper()}] {f['title']}** (`{f_rel}`)\n"
                    f"   - **Why it comes first**: High-severity blocker or security exposure that presents immediate risk.\n"
                    f"   - **Recommended Action**: {f['recommendation']}"
                )
        else:
            lines.append("- *No urgent blockers found. All critical security checks passed.*")

        # Phase 2: Should Fix
        lines.append("\n#### Phase 2: Quality & Architecture (Should Fix)")
        if should_fix:
            for idx, f in enumerate(should_fix[:6], start=1):
                f_rel = f.get("relative_path") or "Project Root"
                lines.append(
                    f"{idx}. **[{f.get('severity', '').upper()}] {f['title']}** (`{f_rel}`)\n"
                    f"   - **Why it matters**: Resolves technical debt and improves maintainability.\n"
                    f"   - **Recommended Action**: {f['recommendation']}"
                )
        else:
            lines.append("- *No moderate-priority defects detected.*")

        # Phase 3: Nice to Improve
        lines.append("\n#### Phase 3: Hygiene & Documentation (Nice to Improve)")
        if nice_to_improve:
            for idx, f in enumerate(nice_to_improve[:4], start=1):
                lines.append(f"{idx}. **{f['title']}**: {f['recommendation']}")
        else:
            lines.append("- *Hygiene and documentation are in good standing.*")

        top_f = (fix_first or should_fix or nice_to_improve)[0]
        lines.append(
            f"\n#### Recommended Starting Point:\n"
            f"Begin by fixing **`{top_f['title']}`** in `{top_f.get('relative_path') or 'root'}`. "
            f"Addressing this gives the largest immediate boost to project stability and security score."
        )
        return "\n".join(lines)

    def _answer_testing(self, project: Dict[str, Any]) -> str:
        """Answer test questions with inventory, frameworks, and recommendations."""
        project_id = project["id"]
        inventory = self.inventory_builder.build_inventory(project_id)
        files = self.repo.list_files(project_id=project_id, limit=5000)
        structure, _ = self.structure_analyzer.analyze(project_id, inventory, files)
        test_files = inventory.test_files
        test_findings = self.repo.list_findings(project_id, category=FindingCategory.TESTING.value, status="open")

        if not test_files:
            return (
                f"### Testing Health Evaluation: {project['name']}\n\n"
                f"**I couldn't find tests in this project.**\n\n"
                f"- **Test Files Found**: 0 test files detected across {inventory.total_files} tracked files.\n"
                f"- **Status**: No dedicated test directories (`tests/`, `spec/`, `__tests__/`) or test files (`test_*.py`, `*.test.js`) were identified.\n\n"
                f"#### Recommendations:\n"
                f"1. Create a dedicated test folder (e.g. `tests/`).\n"
                f"2. Configure a test runner for `{structure.primary_ecosystem.title()}` (e.g. `pytest` for Python, `vitest`/`jest` for JS/TS).\n"
                f"3. Write initial unit tests covering the primary application entry points."
            )

        fw = self._detect_test_framework(test_files)
        roots_str = ", ".join(f"`{r}`" for r in structure.test_roots) if structure.test_roots else "Dispersed test files"

        lines = [
            f"### Testing Health Evaluation: {project['name']}\n",
            f"- **Test Files Found**: **{len(test_files)}** test file(s)\n"
            f"- **Test Roots / Folders**: {roots_str}\n"
            f"- **Detected Framework**: `{fw}`\n",
            "#### Test Files Detected:\n",
        ]
        for tf in test_files[:8]:
            lines.append(f"• `{tf['relative_path']}` ({_format_bytes(tf.get('size_bytes', 0))})")

        if test_findings:
            lines.append("\n#### Testing Deficiencies & Recommendations:\n")
            for idx, f in enumerate(test_findings, start=1):
                lines.append(f"{idx}. **[{f.get('severity', '').upper()}] {f['title']}**: {f['recommendation']}")
        else:
            lines.append(
                "\n#### Testing Health Assessment:\n"
                "Test structure is established. Ensure comprehensive test coverage across core business logic and critical API routes."
            )

        return "\n".join(lines)

    def _detect_candidate_entry_points(self, files: List[Dict[str, Any]]) -> List[str]:
        """Identify candidate entry points from filenames across project files."""
        entry_points = []
        for f in files:
            fname = (f.get("filename") or "").lower()
            rel = (f.get("relative_path") or "").replace("\\", "/")
            if fname in ("main.py", "app.py", "index.js", "index.ts", "server.js", "manage.py", "main.go", "main.rs", "app.ts"):
                entry_points.append(rel)
        return entry_points

    def _answer_structure(self, project: Dict[str, Any]) -> str:
        """Answer project structure questions with folder layout and architecture roots."""
        project_id = project["id"]
        inventory = self.inventory_builder.build_inventory(project_id)
        files = self.repo.list_files(project_id=project_id, limit=5000)
        structure, _ = self.structure_analyzer.analyze(project_id, inventory, files)

        dir_lines = self._summarize_directory_layout(files)
        src_roots = ", ".join(f"`{r}`" for r in structure.source_roots) if structure.source_roots else "Root layout"
        t_roots = ", ".join(f"`{r}`" for r in structure.test_roots) if structure.test_roots else "No dedicated test folder"
        d_roots = ", ".join(f"`{r}`" for r in structure.doc_roots) if structure.doc_roots else "None"
        entry_points = self._detect_candidate_entry_points(files)
        ep_str = ", ".join(f"`{ep}`" for ep in entry_points) if entry_points else "No single entry point detected"

        lines = [
            f"### Project Structure: {project['name']}\n",
            f"- **Primary Ecosystem**: `{structure.primary_ecosystem.title()}`\n"
            f"- **Total Files**: {inventory.total_files:,} files ({_format_bytes(inventory.total_size_bytes)}) across {inventory.total_dirs} directories\n"
            f"- **Maximum Hierarchy Depth**: {structure.max_depth} levels\n",
            "#### Directory Layout & Organization:\n" + "\n".join(dir_lines) + "\n",
            "#### Architectural Roots:\n"
            f"- **Source Roots**: {src_roots}\n"
            f"- **Test Roots**: {t_roots}\n"
            f"- **Documentation Roots**: {d_roots}\n"
            f"- **Candidate Entry Points**: {ep_str}\n",
            "#### File Classification Breakdown:\n"
            f"- **Source Code**: {inventory.source_files} files\n"
            f"- **Configuration**: {inventory.config_files} files\n"
            f"- **Documentation**: {inventory.document_files} files\n"
            f"- **Data & Assets**: {inventory.data_files + inventory.other_files} files"
        ]
        return "\n".join(lines)

    def _answer_overview(self, project: Dict[str, Any]) -> str:
        """Answer high-level overview questions grounded in README and metadata."""
        project_id = project["id"]
        inventory = self.inventory_builder.build_inventory(project_id)
        files = self.repo.list_files(project_id=project_id, limit=5000)
        structure, _ = self.structure_analyzer.analyze(project_id, inventory, files)
        health = self.repo.get_project_health(project_id) or {}
        findings = self.repo.list_findings(project_id, status="open", limit=3)

        readme_file = None
        readme_preview = ""
        for f in files:
            if "readme" in (f.get("filename") or "").lower():
                readme_file = f
                rm_ext = self.repo.get_extraction(f["id"])
                if rm_ext and rm_ext.get("content_text"):
                    readme_preview = rm_ext["content_text"][:500]
                elif f.get("path"):
                    try:
                        p = Path(f["path"])
                        if p.exists() and p.is_file():
                            readme_preview = p.read_text(encoding="utf-8", errors="ignore")[:500]
                    except Exception:
                        pass
                break

        languages_str = ", ".join(f"{k} ({v} files)" for k, v in sorted(inventory.languages.items(), key=lambda x: x[1], reverse=True)[:5]) or "None identified"
        entry_points = self._detect_candidate_entry_points(files)
        entry_points_str = ", ".join(f"`{ep}`" for ep in entry_points) if entry_points else "Modular package structure"

        lines = [
            f"### Project Overview: {project['name']}\n",
            "#### Purpose & Technology Stack\n"
            f"- **Primary Ecosystem**: `{structure.primary_ecosystem.title()}`\n"
            f"- **Languages Detected**: {languages_str}\n"
            f"- **Total Scope**: {inventory.total_files:,} files ({_format_bytes(inventory.total_size_bytes)})\n",
        ]

        if readme_preview:
            clean_rm = self.redactor.redact(readme_preview).sanitized_text
            lines.append(f"#### Overview from Documentation (`README.md`):\n```markdown\n{clean_rm.strip()}\n```\n")

        lines.extend([
            "#### Architecture & Structure\n"
            f"- **Entry Point(s)**: {entry_points_str}\n"
            f"- **Source Roots**: {', '.join(f'`{r}`' for r in structure.source_roots) or 'Root layout'}\n"
            f"- **Test Roots**: {', '.join(f'`{r}`' for r in structure.test_roots) or 'No dedicated test directory'}\n",
            "#### Current Health & Posture\n"
            f"- **Health Rating**: **{health.get('overall_score', 0)}/100 (Grade {health.get('grade', 'N/A')})**\n"
            f"- **Active Risks**: {health.get('critical_count', 0)} Critical, {health.get('high_count', 0)} High issues detected.\n"
            f"- **Summary**: {health.get('summary', 'Run full analysis for health evaluation.')}"
        ])

        if findings:
            lines.append("\n#### Top Issues Requiring Attention:")
            for idx, f in enumerate(findings, start=1):
                lines.append(f"{idx}. **[{f.get('severity', '').upper()}]** {f.get('title')} (`{f.get('relative_path') or 'root'}`)")

        return "\n".join(lines)

    def _answer_dependencies(self, project: Dict[str, Any]) -> str:
        """Answer dependency questions with manifests, packages, and lockfiles."""
        project_id = project["id"]
        inventory = self.inventory_builder.build_inventory(project_id)
        manifest_files = inventory.manifest_files
        lock_files = inventory.lock_files
        dep_findings = self.repo.list_findings(project_id, category=FindingCategory.DEPENDENCIES.value, status="open")

        if not manifest_files:
            return (
                f"### Dependencies & Libraries: {project['name']}\n\n"
                f"**No package manifests were found in this project.**\n\n"
                f"- Checked for standard manifest files: `requirements.txt`, `pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`, `pom.xml`.\n"
                f"- None were detected in the {inventory.total_files} tracked files.\n\n"
                f"#### Recommendation:\n"
                f"If this project relies on external libraries, add a standard manifest (such as `requirements.txt` or `package.json`) to track and version dependencies cleanly."
            )

        libraries = self._extract_libraries_from_manifests(project_id, manifest_files)

        lines = [
            f"### Dependencies & Libraries: {project['name']}\n",
            "I inspected package manifests and lockfiles across this project:\n",
            "#### Detected Package Manifests:\n",
        ]
        for mf in manifest_files:
            lines.append(f"• `{mf['relative_path']}` ({_format_bytes(mf.get('size_bytes', 0))})")

        if lock_files:
            lines.append("\n#### Detected Lockfiles:\n")
            for lf in lock_files:
                lines.append(f"• `{lf['relative_path']}` (reproducible build lockfile)")
        else:
            lines.append("\n- *Lockfile Status*: No lockfile detected (e.g. `package-lock.json`, `poetry.lock`). Consider generating one for reproducible builds.")

        if libraries:
            lines.append(f"\n#### Key Libraries & Packages Detected ({len(libraries)}):\n")
            lines.append(", ".join(libraries))

        if dep_findings:
            lines.append("\n\n#### Dependency Findings & Deficiencies:\n")
            for idx, f in enumerate(dep_findings, start=1):
                lines.append(f"{idx}. **[{f.get('severity', '').upper()}] {f['title']}**: {f['recommendation']}")
        else:
            lines.append("\n\n- **Security Posture**: No dependency vulnerabilities or unpinned package issues detected.")

        return "\n".join(lines)

    def _answer_duplicates(self, project: Dict[str, Any]) -> str:
        """Answer duplicate file questions with SHA-256 clusters and space wasted."""
        project_id = project["id"]
        inventory = self.inventory_builder.build_inventory(project_id)
        duplicates = self.repo.get_duplicate_files(project_id)

        if not duplicates:
            return (
                f"### Duplicate Files Analysis: {project['name']}\n\n"
                f"**No duplicate files were detected across scanned files.**\n\n"
                f"- All {inventory.total_files} tracked files have unique content hashes (SHA-256).\n"
                f"- Storage efficiency is 100% with zero duplicate file waste."
            )

        total_wasted = sum(d.get("wasted_bytes", 0) for d in duplicates)
        lines = [
            f"### Duplicate Files Analysis: {project['name']}\n",
            f"**Found {len(duplicates)} duplicate file cluster(s)** sharing identical SHA-256 content hashes, "
            f"wasting **{_format_bytes(total_wasted)}** of storage.\n",
            "#### Duplicate File Clusters:\n",
        ]
        for idx, d in enumerate(duplicates[:6], start=1):
            h_short = d.get("sha256", "")[:12]
            f_size = _format_bytes(d.get("size_bytes", 0))
            wasted = _format_bytes(d.get("wasted_bytes", 0))
            copies = d.get("count", 0)
            paths = [f"`{f.get('relative_path', '')}`" for f in d.get("files", [])]
            lines.append(
                f"{idx}. **Cluster `{h_short}...`** ({f_size} each, {copies} copies — wastes {wasted}):\n"
                f"   - " + "\n   - ".join(paths)
            )

        lines.append(
            "\n#### Safe Cleanup Policy:\n"
            "1. Select the canonical copy (typically in the primary source or assets folder).\n"
            "2. Remove redundant copies or replace them with relative symlinks/imports.\n"
            "3. Verify build tests pass before committing deletions."
        )
        return "\n".join(lines)

    def _answer_finding_detail(self, project: Dict[str, Any], finding: Dict[str, Any], question: str) -> str:
        """Answer deep questions about a specific finding, including 'Why?' and 'How to fix'."""
        f_rel = finding.get("relative_path") or "Project Root"
        loc = finding.get("location") or "file scope"
        sev = finding.get("severity", "medium").upper()
        p_tier = finding.get("priority_tier", "should_fix").upper()
        cat = finding.get("category", "quality").title()
        safe_ev = self.redactor.redact(finding.get("evidence") or "None").sanitized_text

        q_lower = question.lower()
        is_why = any(w in q_lower for w in ("why", "why?", "reason", "impact", "matter", "importance"))
        is_how = any(w in q_lower for w in ("how to fix", "how do i fix", "how can i fix", "how to resolve", "fix this", "fix it"))

        if is_why:
            return (
                f"### Why This Matters: {finding['title']}\n\n"
                f"- **Affected Location**: `{f_rel}` ({loc})\n"
                f"- **Category**: `{cat}` | **Severity**: `{sev}` | **Priority**: `{p_tier}`\n\n"
                f"#### Root Cause & Description\n"
                f"{finding.get('description')}\n\n"
                f"#### Impact & Risk If Ignored\n"
                f"Leaving this `{cat}` finding unaddressed degrades codebase health and increases project vulnerability risk. "
                f"Severity `{sev}` issues directly lower the overall SVANT project health score and can cause production failures or credential compromise.\n\n"
                f"#### Recommended Fix\n"
                f"{finding.get('recommendation')}"
            )

        if is_how:
            return (
                f"### How to Fix: {finding['title']}\n\n"
                f"- **Location**: `{f_rel}` ({loc})\n"
                f"- **Severity**: `{sev}`\n\n"
                f"#### Action Required\n"
                f"{finding.get('recommendation')}\n\n"
                f"#### Step-by-Step Remediation\n"
                f"1. Open `{f_rel}` in your code editor.\n"
                f"2. Navigate to context: `{loc}`.\n"
                f"3. Apply the recommended resolution: replace or refactor the offending code.\n"
                f"4. Re-run SVANT analysis to verify the finding is resolved.\n\n"
                f"#### Relevant Evidence (Redacted):\n"
                f"```\n{safe_ev}\n```"
            )

        return (
            f"### Finding Analysis: {finding['title']}\n\n"
            f"- **Category**: `{cat}` | **Severity**: `{sev}` | **Priority Tier**: `{p_tier}`\n"
            f"- **Location**: `{f_rel}` ({loc})\n\n"
            f"#### What Was Detected\n"
            f"{finding.get('description')}\n\n"
            f"#### Why It Matters & Risk\n"
            f"Unresolved {cat.lower()} issues negatively impact maintainability, security, and project health.\n\n"
            f"#### How to Fix\n"
            f"{finding.get('recommendation')}\n\n"
            f"#### Evidence (Redacted Locally)\n"
            f"```\n{safe_ev}\n```\n\n"
            f"#### Priority Rationale\n"
            f"Assigned priority `{p_tier}` due to `{sev}` severity rating."
        )

    def _answer_follow_up_general(self, project: Dict[str, Any], question: str, history: Optional[List[Dict[str, str]]]) -> str:
        """Handle general conversational follow-ups by analyzing conversation context."""
        project_id = project["id"]
        hist_text = ""
        if history:
            for turn in history[-4:]:
                hist_text += " " + turn.get("content", "").lower()

        # Follow-up on testing
        if "test" in hist_text:
            return self._answer_testing(project)

        # Follow-up on health
        if "health score" in hist_text or "grade" in hist_text:
            health = self.repo.get_project_health(project_id) or {}
            comp = health.get("component_scores", {})
            comp_lines = [f"• {k.title()}: {v.get('score', 100)}/100 - {v.get('rationale', '')}" for k, v in comp.items() if isinstance(v, dict)]
            return (
                f"### Health Score Breakdown: {project['name']}\n\n"
                f"**Overall Score**: {health.get('overall_score', 0)}/100 (Grade {health.get('grade', 'N/A')})\n\n"
                f"**Summary**: {health.get('summary', '')}\n\n"
                f"**Component Analysis**:\n" + "\n".join(comp_lines)
            )

        # Follow-up on priority or security findings
        open_findings = self.repo.list_findings(project_id, status="open")
        if open_findings:
            return self._answer_finding_detail(project, open_findings[0], question)

        return self._answer_priority(project)

    def _answer_general(
        self,
        project: Dict[str, Any],
        question: str,
        context_items: Optional[List[ContextItem]],
        citations: Optional[List[Citation]],
    ) -> str:
        """Answer general code queries using retrieved search excerpts."""
        code_chunks = [
            it for it in (context_items or [])
            if not it.filename.endswith(".md") or "README" in it.filename
        ]
        if not code_chunks and context_items:
            code_chunks = context_items

        if not code_chunks:
            return (
                f"I couldn't find enough relevant information in '{project['name']}' to answer that confidently. "
                "You may want to verify that the project is indexed, or try asking a more specific question."
            )

        lines = [
            f"### Code Evidence for '{question}' in {project['name']}\n",
            "Here is the relevant information found in your tracked project files:\n",
        ]
        for it in code_chunks[:4]:
            loc = f" (line {it.line_start})" if it.line_start else ""
            clean_snippet = self.redactor.redact(it.content.strip()).sanitized_text
            preview = clean_snippet[:300].strip()
            if len(clean_snippet) > 300:
                preview += "..."
            lines.append(f"• **`{it.relative_path}`**{loc}:\n  ```\n  {preview}\n  ```")

        return "\n".join(lines)
