"""
Smart Context Selector for SVANT Phase 6 & 7.
Analyzes query intent and dynamically enriches RAG context with structured project
intelligence (overview, architecture, health, security, findings, dependencies, duplicates)
alongside hybrid search chunks within strict context token/character budgets.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple

from svant.config import settings
from svant.core.intelligence.models import FindingCategory, PriorityTier
from svant.core.rag.context import ContextAssembler, ContextCategory, ContextItem
from svant.core.search import SearchMode, SearchService
from svant.db.repository import Repository
from svant.logger import get_logger

logger = get_logger("svant.core.rag.smart_selector")


class QueryIntent:
    SECURITY = "SECURITY"
    ARCHITECTURE = "ARCHITECTURE"
    STRUCTURE = "STRUCTURE"
    HEALTH = "HEALTH"
    PRIORITY = "PRIORITY"
    ONBOARDING = "ONBOARDING"
    TESTING = "TESTING"
    DEPENDENCIES = "DEPENDENCIES"
    DOCUMENTATION = "DOCUMENTATION"
    HYGIENE = "HYGIENE"
    DUPLICATES = "DUPLICATES"
    FINDING_DETAIL = "FINDING_DETAIL"
    FOLLOW_UP = "FOLLOW_UP"
    GENERAL = "GENERAL"


class SmartContextSelector:
    """Intelligently detects query intent and synthesizes multi-category project context."""

    def __init__(
        self,
        repo: Repository,
        search_service: Optional[SearchService] = None,
        assembler: Optional[ContextAssembler] = None,
    ) -> None:
        self.repo = repo
        self.search_service = search_service or SearchService(repo)
        self.assembler = assembler or ContextAssembler()

    def classify_intent(
        self,
        query: str,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> List[str]:
        """Identify matching intent categories from query terms, history, and syntax."""
        q = query.lower().strip()
        intents: List[str] = []

        # 0. Follow-up & Finding Detail checks
        is_ordinal = any(w in q for w in ("first", "1st", "#1", "number 1", "second", "2nd", "#2", "number 2", "third", "3rd", "#3", "number 3", "fourth", "4th", "#4", "number 4"))
        is_follow_up_phrase = any(w in q for w in ("why", "why?", "tell me more", "how do i fix", "how to fix", "how do i resolve", "elaborate", "more detail", "what about", "that finding", "that issue"))

        if is_ordinal or (is_follow_up_phrase and history):
            intents.append(QueryIntent.FOLLOW_UP)
            intents.append(QueryIntent.FINDING_DETAIL)

        # 1. Security
        if any(w in q for w in ("security", "secret", "secrets", "credential", "credentials", "password", "passwords", "token", "tokens", "private key", "vulnerability", "vulnerabilities", "leak", "exposure", "auth key", "cve", "insecure", "unsafe", "security problems", "security issues")):
            intents.append(QueryIntent.SECURITY)

        # 2. Priority & What to fix first
        if any(w in q for w in ("fix first", "what to fix", "what should i fix", "priority", "priorities", "remediation", "action plan", "biggest problems", "worst issues", "top issues", "what would you improve", "improve", "improvements", "suggest improvements", "what to improve", "recommendations", "what should i do first", "what needs attention")):
            intents.append(QueryIntent.PRIORITY)

        # 3. Health & Scoring
        if any(w in q for w in ("health", "score", "grade", "why is score", "why is my score", "health score", "audit", "status", "how healthy", "rating")):
            intents.append(QueryIntent.HEALTH)

        # 4. Structure
        if any(w in q for w in ("project structure", "folder structure", "directory structure", "file structure", "explain my project structure", "explain structure", "code organization", "how is it organized", "folder layout", "directory hierarchy", "file organization", "architecture layout")):
            intents.append(QueryIntent.STRUCTURE)

        # 5. Architecture & Overview
        if any(w in q for w in ("how does this project work", "how does it work", "architecture", "overview", "what does this project do", "what is this project", "explain project", "explain my project", "explain the project", "explain this project", "about the project", "project overview", "entry point", "main component", "system design")):
            intents.append(QueryIntent.ARCHITECTURE)

        # 6. Onboarding & Getting Started
        if any(w in q for w in ("onboard", "onboarding", "get started", "getting started", "how to start", "new contributor", "setup instructions", "run this project", "how to run", "how to build")):
            intents.append(QueryIntent.ONBOARDING)

        # 7. Testing
        if any(w in q for w in ("test", "tests", "testing", "coverage", "pytest", "unittest", "spec", "specs", "how good are my tests", "are there tests", "test suite")):
            intents.append(QueryIntent.TESTING)

        # 8. Dependencies & Libraries
        if any(w in q for w in ("dependenc", "package", "packages", "manifest", "manifests", "requirements.txt", "package.json", "pyproject.toml", "lockfile", "lockfiles", "pip", "npm", "cargo", "go.mod", "librar", "libraries", "library", "module", "modules", "third-party", "third party")):
            intents.append(QueryIntent.DEPENDENCIES)

        # 9. Duplicates
        if any(w in q for w in ("duplicate", "duplicates", "redundant", "identical file", "identical files", "wasted space", "storage waste", "duplicate files", "clones")):
            intents.append(QueryIntent.DUPLICATES)

        # 10. Documentation
        if any(w in q for w in ("documentation", "readme", "doc", "docs", "license", "guidelines", "changelog")):
            intents.append(QueryIntent.DOCUMENTATION)

        # 11. Hygiene
        if any(w in q for w in ("hygiene", "clutter", "stale", "clean up", "todo", "todos")):
            intents.append(QueryIntent.HYGIENE)

        if not intents:
            intents.append(QueryIntent.GENERAL)

        return intents

    def build_context(
        self,
        project_id: str,
        query: str,
        search_mode: SearchMode = SearchMode.HYBRID,
        top_k: Optional[int] = None,
        referenced_finding: Optional[Dict[str, Any]] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> List[ContextItem]:
        """
        Build a prioritized, structured list of context items tailored to query intent
        and bounded by character budget.
        """
        intents = self.classify_intent(query, history=history)
        logger.debug(f"SmartContextSelector identified intents {intents} for query '{query}'")

        limit_k = top_k or self.assembler.top_k
        max_chars = self.assembler.max_context_chars

        intel_items: List[ContextItem] = []
        seen_keys: Set[str] = set()
        accumulated_chars = 0

        def _add_item(item: ContextItem) -> bool:
            nonlocal accumulated_chars
            dedup_key = f"{item.file_id}:{item.relative_path}:{item.citation_label}:{item.content[:80]}"
            if dedup_key in seen_keys:
                return False
            seen_keys.add(dedup_key)

            item_len = len(item.content)
            if accumulated_chars + item_len > max_chars:
                remaining = max_chars - accumulated_chars
                if remaining < 150:
                    return False
                item.content = item.content[:remaining] + "\n... [truncated to fit context budget]"
                item_len = len(item.content)

            intel_items.append(item)
            accumulated_chars += item_len
            return True

        # A. If there is an explicitly referenced finding (e.g. from follow-up or explicit ID)
        if referenced_finding:
            f_rel = referenced_finding.get("relative_path") or "Project Root"
            f_content = (
                f"Referenced Finding [{referenced_finding.get('severity', '').upper()}]: {referenced_finding.get('title')}\n"
                f"Category: {referenced_finding.get('category')} | Priority: {referenced_finding.get('priority_tier')}\n"
                f"File: {f_rel} ({referenced_finding.get('location') or 'file'})\n"
                f"Description: {referenced_finding.get('description')}\n"
                f"Evidence: {referenced_finding.get('evidence') or 'N/A'}\n"
                f"Recommendation: {referenced_finding.get('recommendation')}"
            )
            _add_item(ContextItem(
                file_id=referenced_finding.get("file_id") or "ref-finding",
                chunk_id=referenced_finding.get("id"),
                filename=f_rel.split("/")[-1].split("\\")[-1] or "finding",
                relative_path=f_rel,
                project_id=project_id,
                chunk_index=0,
                content=f_content,
                relevance_score=1.0,
                section="Referenced Finding",
                category=ContextCategory.SECURITY_FINDINGS.value if referenced_finding.get("category") == "security" else ContextCategory.QUALITY_FINDINGS.value,
            ))

        # B. Intent-driven intelligence injection
        health_data = self.repo.get_project_health(project_id)
        project = self.repo.get_project(project_id)

        # 1. Health & Priority context
        if QueryIntent.HEALTH in intents or QueryIntent.PRIORITY in intents:
            if health_data:
                comp_scores = health_data.get("component_scores", {})
                breakdown_lines = []
                for cat_name, c_info in comp_scores.items():
                    if isinstance(c_info, dict):
                        breakdown_lines.append(f"• {cat_name.title()}: {c_info.get('score', 100)}/100 (Weight: {c_info.get('weight', 0):.0%}) - {c_info.get('rationale', '')}")
                breakdown_txt = "\n".join(breakdown_lines)

                h_txt = (
                    f"SVANT Project Health Score: {health_data.get('overall_score', 0)}/100 (Grade {health_data.get('grade', 'N/A')})\n"
                    f"Summary: {health_data.get('summary', '')}\n"
                    f"Issues Summary: {health_data.get('critical_count', 0)} Critical, {health_data.get('high_count', 0)} High, "
                    f"{health_data.get('medium_count', 0)} Medium, {health_data.get('low_count', 0)} Low.\n"
                    f"Component Breakdown:\n{breakdown_txt}"
                )
                _add_item(ContextItem(
                    file_id="project-health-score",
                    chunk_id="health-overview",
                    filename="PROJECT_HEALTH.md",
                    relative_path="PROJECT_HEALTH.md",
                    project_id=project_id,
                    chunk_index=0,
                    content=h_txt,
                    relevance_score=0.98,
                    section="Health Breakdown",
                    category=ContextCategory.PROJECT_HEALTH.value,
                ))

        # 2. Priority "Fix First" findings
        if QueryIntent.PRIORITY in intents:
            fix_first = self.repo.list_findings(project_id, priority_tier=PriorityTier.FIX_FIRST.value, status="open", limit=6)
            should_fix = self.repo.list_findings(project_id, priority_tier=PriorityTier.SHOULD_FIX.value, status="open", limit=4)
            if fix_first or should_fix:
                for idx, f in enumerate(fix_first + should_fix):
                    f_rel = f.get("relative_path") or "Project Root"
                    f_txt = (
                        f"Priority Action [{f.get('priority_tier', '').upper()}] ({f.get('severity', '').upper()}): {f.get('title')}\n"
                        f"Location: {f_rel} ({f.get('location') or 'file'})\n"
                        f"Description: {f.get('description')}\n"
                        f"Recommendation: {f.get('recommendation')}\n"
                        f"Evidence: {f.get('evidence') or 'None'}"
                    )
                    _add_item(ContextItem(
                        file_id=f.get("file_id") or f"priority-{idx}",
                        chunk_id=f.get("id"),
                        filename=f_rel.split("/")[-1].split("\\")[-1] or "finding",
                        relative_path=f_rel,
                        project_id=project_id,
                        chunk_index=idx,
                        content=f_txt,
                        relevance_score=0.96 - (idx * 0.01),
                        section=f"Priority: {f.get('priority_tier')}",
                        category=ContextCategory.SECURITY_FINDINGS.value if f.get("category") == "security" else ContextCategory.QUALITY_FINDINGS.value,
                    ))
            else:
                _add_item(ContextItem(
                    file_id="priority-status-clean",
                    chunk_id="priority-clean",
                    filename="PRIORITY.md",
                    relative_path="PRIORITY.md",
                    project_id=project_id,
                    chunk_index=0,
                    content="Priority Status: No urgent defects or priority findings detected in this project. All scans passed with zero open issues.",
                    relevance_score=0.96,
                    section="Priority Status",
                    category=ContextCategory.QUALITY_FINDINGS.value,
                ))

        # 3. Security findings
        if QueryIntent.SECURITY in intents:
            sec_findings = self.repo.list_findings(project_id, category=FindingCategory.SECURITY.value, status="open", limit=8)
            if sec_findings:
                for idx, f in enumerate(sec_findings):
                    f_rel = f.get("relative_path") or "Project Root"
                    f_txt = (
                        f"Security Finding [{f.get('severity', '').upper()}]: {f.get('title')}\n"
                        f"File: {f_rel} ({f.get('location') or 'file'})\n"
                        f"Description: {f.get('description')}\n"
                        f"Evidence: {f.get('evidence') or 'None'}\n"
                        f"Remediation: {f.get('recommendation')}"
                    )
                    _add_item(ContextItem(
                        file_id=f.get("file_id") or f"sec-{idx}",
                        chunk_id=f.get("id"),
                        filename=f_rel.split("/")[-1].split("\\")[-1] or "security",
                        relative_path=f_rel,
                        project_id=project_id,
                        chunk_index=idx,
                        content=f_txt,
                        relevance_score=0.97 - (idx * 0.01),
                        section="Security Finding",
                        category=ContextCategory.SECURITY_FINDINGS.value,
                    ))
            else:
                _add_item(ContextItem(
                    file_id="sec-status-clean",
                    chunk_id="sec-clean",
                    filename="SECURITY.md",
                    relative_path="SECURITY.md",
                    project_id=project_id,
                    chunk_index=0,
                    content="Security Status: No security vulnerabilities, leaked credentials, or hardcoded secrets detected in this project.",
                    relevance_score=0.96,
                    section="Security Status",
                    category=ContextCategory.SECURITY_FINDINGS.value,
                ))

        # 4. Architecture / Onboarding / Structure context
        if QueryIntent.ARCHITECTURE in intents or QueryIntent.ONBOARDING in intents or QueryIntent.STRUCTURE in intents:
            files = self.repo.list_files(project_id=project_id, limit=2000)
            total_files = len(files)
            ext_counts: Dict[str, int] = {}
            readme_file = None
            entry_points: List[str] = []
            dir_counts: Dict[str, int] = {}

            for f in files:
                ext = f.get("extension", "").lower()
                ext_counts[ext] = ext_counts.get(ext, 0) + 1
                rel = (f.get("relative_path") or "").replace("\\", "/")
                fname_lower = (f.get("filename") or "").lower()

                parts = rel.split("/")
                if len(parts) > 1:
                    dir_counts[parts[0] + "/"] = dir_counts.get(parts[0] + "/", 0) + 1
                else:
                    dir_counts["[root]"] = dir_counts.get("[root]", 0) + 1

                if "readme" in fname_lower:
                    readme_file = f
                if fname_lower in ("main.py", "app.py", "index.js", "index.ts", "server.js", "manage.py", "wsgi.py", "asgi.py", "main.go", "main.rs"):
                    entry_points.append(rel)

            dir_summary = ", ".join(f"{d} ({cnt})" for d, cnt in sorted(dir_counts.items(), key=lambda x: x[1], reverse=True)[:6])

            arch_txt = (
                f"Project Overview & Structure:\n"
                f"• Project Name: {project.get('name') if project else 'Unknown'}\n"
                f"• Total Tracked Files: {total_files}\n"
                f"• Key Folders: {dir_summary}\n"
                f"• Key Extensions: {', '.join(f'{k} ({v})' for k, v in sorted(ext_counts.items(), key=lambda x: x[1], reverse=True)[:6])}\n"
                f"• Candidate Entry Points: {', '.join(entry_points) if entry_points else 'No standard single entry point detected.'}\n"
            )
            _add_item(ContextItem(
                file_id="project-structure-summary",
                chunk_id="struct-0",
                filename="STRUCTURE.md",
                relative_path="STRUCTURE.md",
                project_id=project_id,
                chunk_index=0,
                content=arch_txt,
                relevance_score=0.95,
                section="Structure Overview",
                category=ContextCategory.PROJECT_STRUCTURE.value,
            ))

            # If README is present, grab its content preview or extract
            if readme_file:
                r_preview = ""
                rm_ext = self.repo.get_extraction(readme_file["id"])
                if rm_ext and rm_ext.get("content_text"):
                    r_preview = rm_ext["content_text"][:2000]
                elif readme_file.get("path"):
                    try:
                        p = Path(readme_file["path"])
                        if p.exists() and p.is_file():
                            r_preview = p.read_text(encoding="utf-8", errors="ignore")[:2000]
                    except Exception:
                        pass
                if r_preview:
                    _add_item(ContextItem(
                        file_id=readme_file["id"],
                        chunk_id=f"readme-{readme_file['id']}",
                        filename=readme_file["filename"],
                        relative_path=readme_file["relative_path"],
                        project_id=project_id,
                        chunk_index=0,
                        content=f"README Documentation Excerpt:\n{r_preview}",
                        relevance_score=0.94,
                        section="README",
                        category=ContextCategory.DOCUMENTATION_FINDINGS.value,
                    ))

        # 5. Duplicates context
        if QueryIntent.DUPLICATES in intents:
            duplicates = self.repo.get_duplicate_files(project_id)
            if duplicates:
                dup_lines = []
                for d in duplicates[:5]:
                    paths = [f.get("relative_path", "") for f in d.get("files", [])]
                    dup_lines.append(f"• Hash {d.get('sha256', '')[:12]} ({d.get('size_bytes', 0)} bytes, {d.get('count', 0)} copies): {', '.join(paths)}")
                dup_txt = "Duplicate File Clusters Detected (Identical SHA-256):\n" + "\n".join(dup_lines)
            else:
                dup_txt = "Duplicate File Status: No duplicate files were detected across scanned files (0 identical SHA-256 hashes)."

            _add_item(ContextItem(
                file_id="duplicates-summary",
                chunk_id="dups-0",
                filename="DUPLICATES.md",
                relative_path="DUPLICATES.md",
                project_id=project_id,
                chunk_index=0,
                content=dup_txt,
                relevance_score=0.95,
                section="Duplicates",
                category=ContextCategory.DUPLICATES.value,
            ))

        # 6. Testing context
        if QueryIntent.TESTING in intents:
            all_files = self.repo.list_files(project_id=project_id, limit=2000)
            test_files = [f for f in all_files if "test" in (f.get("filename") or "").lower() or "/test" in (f.get("relative_path") or "").replace("\\", "/").lower()]
            test_findings = self.repo.list_findings(project_id, category=FindingCategory.TESTING.value, status="open", limit=5)

            if test_files:
                test_paths = [f.get("relative_path", "") for f in test_files[:8]]
                test_summary = f"Testing Inventory: Found {len(test_files)} test file(s):\n• " + "\n• ".join(test_paths)
            else:
                test_summary = "Testing Inventory: No test files or dedicated test directories detected in this project."

            _add_item(ContextItem(
                file_id="testing-inventory",
                chunk_id="test-inv-0",
                filename="TESTING.md",
                relative_path="TESTING.md",
                project_id=project_id,
                chunk_index=0,
                content=test_summary,
                relevance_score=0.94,
                section="Testing Inventory",
                category=ContextCategory.TESTING_FINDINGS.value,
            ))

            for idx, f in enumerate(test_findings):
                f_rel = f.get("relative_path") or "Test Suite"
                f_txt = (
                    f"Testing Finding [{f.get('severity', '').upper()}]: {f.get('title')}\n"
                    f"Location: {f_rel}\n"
                    f"Description: {f.get('description')}\n"
                    f"Recommendation: {f.get('recommendation')}"
                )
                _add_item(ContextItem(
                    file_id=f.get("file_id") or f"test-{idx}",
                    chunk_id=f.get("id"),
                    filename=f_rel.split("/")[-1].split("\\")[-1] or "test",
                    relative_path=f_rel,
                    project_id=project_id,
                    chunk_index=idx,
                    content=f_txt,
                    relevance_score=0.92,
                    section="Testing Health",
                    category=ContextCategory.TESTING_FINDINGS.value,
                ))

        # 7. Dependencies context
        if QueryIntent.DEPENDENCIES in intents:
            all_files = self.repo.list_files(project_id=project_id, limit=2000)
            manifest_names = {"requirements.txt", "pyproject.toml", "package.json", "cargo.toml", "go.mod", "pom.xml", "build.gradle"}
            manifest_files = [f for f in all_files if (f.get("filename") or "").lower() in manifest_names or (f.get("filename") or "").lower().endswith((".csproj", ".lock"))]
            dep_findings = self.repo.list_findings(project_id, category=FindingCategory.DEPENDENCIES.value, status="open", limit=5)

            if manifest_files:
                mf_lines = [f"• {f.get('filename')}: `{f.get('relative_path')}`" for f in manifest_files]
                dep_summary = "Detected Package Manifests & Lockfiles:\n" + "\n".join(mf_lines)
                # Preview top manifest content
                top_mf = manifest_files[0]
                mf_text = ""
                mf_ext = self.repo.get_extraction(top_mf["id"])
                if mf_ext and mf_ext.get("content_text"):
                    mf_text = mf_ext["content_text"][:1500]
                elif top_mf.get("path"):
                    try:
                        p = Path(top_mf["path"])
                        if p.exists() and p.is_file():
                            mf_text = p.read_text(encoding="utf-8", errors="ignore")[:1500]
                    except Exception:
                        pass
                if mf_text:
                    dep_summary += f"\n\nManifest Content Preview ({top_mf.get('filename')}):\n" + mf_text
            else:
                dep_summary = "Dependencies & Manifests: No standard package manifests (requirements.txt, package.json, etc.) detected in this project."

            _add_item(ContextItem(
                file_id="dependencies-inventory",
                chunk_id="dep-inv-0",
                filename="DEPENDENCIES.md",
                relative_path="DEPENDENCIES.md",
                project_id=project_id,
                chunk_index=0,
                content=dep_summary,
                relevance_score=0.94,
                section="Dependencies Inventory",
                category=ContextCategory.DEPENDENCY_FINDINGS.value,
            ))

            for idx, f in enumerate(dep_findings):
                f_rel = f.get("relative_path") or "Dependencies"
                f_txt = (
                    f"Dependency Finding [{f.get('severity', '').upper()}]: {f.get('title')}\n"
                    f"Location: {f_rel}\n"
                    f"Description: {f.get('description')}\n"
                    f"Recommendation: {f.get('recommendation')}"
                )
                _add_item(ContextItem(
                    file_id=f.get("file_id") or f"dep-{idx}",
                    chunk_id=f.get("id"),
                    filename=f_rel.split("/")[-1].split("\\")[-1] or "dependency",
                    relative_path=f_rel,
                    project_id=project_id,
                    chunk_index=idx,
                    content=f_txt,
                    relevance_score=0.92,
                    section="Dependencies",
                    category=ContextCategory.DEPENDENCY_FINDINGS.value,
                ))

        # C. Retrieve Hybrid/Semantic/Keyword search chunks from indexed codebase
        try:
            search_hits = self.search_service.search(
                query=query,
                project_id=project_id,
                mode=search_mode,
                limit=limit_k,
            )
            raw_search_items = self.assembler.assemble(search_hits, project_id=project_id)
            for s_item in raw_search_items:
                _add_item(s_item)
        except Exception as e:
            logger.warning(f"Search retrieval encountered an issue for query '{query}': {e}")

        logger.debug(f"SmartContextSelector assembled {len(intel_items)} items ({accumulated_chars} chars)")
        return intel_items
