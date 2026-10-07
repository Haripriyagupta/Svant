"""
Master Project Intelligence Engine for SVANT (Phase 4 & 5).
Orchestrates inventory gathering, structural analysis, security scanning,
dependency checks, test metrics, documentation evaluation, code hygiene,
quality heuristics, explainable health scoring, and priority ranking.
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional

from svant.core.intelligence.dependencies import DependencyAnalyzer
from svant.core.intelligence.documentation import DocumentationAnalyzer
from svant.core.intelligence.hygiene import HygieneAnalyzer
from svant.core.intelligence.inventory import ProjectInventoryBuilder
from svant.core.intelligence.models import (
    Finding,
    FindingCategory,
    FindingSeverity,
    HealthScore,
    PriorityTier,
    ProjectInventory,
    StructureAnalysis,
)
from svant.core.intelligence.prioritization import PrioritizationEngine
from svant.core.intelligence.quality import QualityAnalyzer
from svant.core.intelligence.scoring import HealthScorer
from svant.core.intelligence.security import SecurityAnalyzer
from svant.core.intelligence.structure import ProjectStructureAnalyzer
from svant.core.intelligence.testing import TestingAnalyzer
from svant.core.privacy.redactor import SecretRedactor
from svant.db.repository import Repository
from svant.logger import get_logger

logger = get_logger("svant.core.intelligence.analyzer")


class ProjectIntelligenceEngine:
    """
    Central coordinator for SVANT Project Intelligence & Health Analysis.
    Ensures safe concurrent execution, robust persistence, and zero secret exposure.
    """

    def __init__(
        self,
        repo: Repository,
        redactor: Optional[SecretRedactor] = None,
    ) -> None:
        self.repo = repo
        self.redactor = redactor or SecretRedactor()
        self.inventory_builder = ProjectInventoryBuilder(repo)
        self.structure_analyzer = ProjectStructureAnalyzer()
        self.security_analyzer = SecurityAnalyzer(repo, self.redactor)
        self.dependency_analyzer = DependencyAnalyzer(repo)
        self.testing_analyzer = TestingAnalyzer()
        self.documentation_analyzer = DocumentationAnalyzer(repo)
        self.hygiene_analyzer = HygieneAnalyzer(repo)
        self.quality_analyzer = QualityAnalyzer(repo)
        self.scorer = HealthScorer()
        self.prioritizer = PrioritizationEngine()

        # Thread synchronization per project
        self._locks: Dict[str, threading.Lock] = {}
        self._global_lock = threading.Lock()

    def _get_project_lock(self, project_id: str) -> threading.Lock:
        with self._global_lock:
            if project_id not in self._locks:
                self._locks[project_id] = threading.Lock()
            return self._locks[project_id]

    def run_analysis(self, project_id: str) -> Dict[str, Any]:
        """
        Execute full intelligence, health, and security analysis for a project.
        Persists results in SQLite and returns comprehensive report.
        """
        lock = self._get_project_lock(project_id)
        if not lock.acquire(blocking=False):
            raise RuntimeError(f"Analysis for project '{project_id}' is already in progress.")

        run_id = self.repo.create_analysis_run(project_id)
        try:
            logger.info("Starting project intelligence analysis", extra={"project_id": project_id, "run_id": run_id})

            project = self.repo.get_project(project_id)
            if not project:
                raise ValueError(f"Project '{project_id}' does not exist.")

            # 1. Fetch tracked files from database
            files = self.repo.list_files(project_id=project_id, limit=100000)

            # 2. Build Inventory
            inventory = self.inventory_builder.build_inventory(project_id)

            # 3. Structural & Ecosystem Analysis
            structure_analysis, structure_findings = self.structure_analyzer.analyze(
                project_id, inventory, files
            )

            # 4. Security & Credential Scanning (Zero raw secrets)
            security_findings = self.security_analyzer.analyze(project_id, files)

            # 5. Dependency Manifest Analysis
            dep_summary, dep_findings = self.dependency_analyzer.analyze(project_id, files)

            # 6. Test Suite Health Analysis
            test_metrics, test_findings = self.testing_analyzer.analyze(
                project_id, inventory, structure_analysis, files
            )

            # 7. Documentation Quality Analysis
            doc_metrics, doc_findings = self.documentation_analyzer.analyze(
                project_id, inventory, structure_analysis, files
            )

            # 8. Hygiene & Duplicate Files Analysis
            hygiene_metrics, hygiene_findings = self.hygiene_analyzer.analyze(
                project_id, inventory, files
            )

            # 9. Quality & Tech Debt Heuristics
            quality_metrics, quality_findings = self.quality_analyzer.analyze(
                project_id, files
            )

            # Aggregate all findings
            all_findings: List[Finding] = (
                security_findings
                + dep_findings
                + test_findings
                + doc_findings
                + hygiene_findings
                + quality_findings
                + structure_findings
            )

            # 10. Prioritize findings into Action Tiers
            prioritized_findings = self.prioritizer.prioritize_findings(all_findings)

            # 11. Calculate Explainable SVANT Health Score (0-100)
            health_score = self.scorer.calculate_health_score(prioritized_findings)

            # 12. Persist findings to SQLite
            finding_dicts = [f.to_dict() for f in prioritized_findings]
            self.repo.upsert_findings(project_id, finding_dicts)

            # 13. Persist health score to SQLite
            health_dict = health_score.to_dict()
            self.repo.upsert_project_health(project_id, health_dict)

            # 14. Mark analysis run completed
            self.repo.update_analysis_run(
                run_id,
                status="completed",
                summary=health_score.summary,
                findings_count=len(prioritized_findings),
                health_score=health_score.overall_score,
            )

            logger.info(
                "Completed project intelligence analysis",
                extra={
                    "project_id": project_id,
                    "score": health_score.overall_score,
                    "grade": health_score.grade,
                    "findings": len(prioritized_findings),
                },
            )

            return {
                "project_id": project_id,
                "health": health_dict,
                "findings": finding_dicts,
                "inventory": inventory.to_dict(),
                "structure": structure_analysis.to_dict(),
                "dependencies": dep_summary,
                "testing": test_metrics,
                "documentation": doc_metrics,
                "hygiene": hygiene_metrics,
                "quality": quality_metrics,
            }

        except Exception as exc:
            logger.error("Project analysis failed", exc_info=True, extra={"project_id": project_id, "run_id": run_id})
            self.repo.update_analysis_run(
                run_id,
                status="failed",
                error_message=str(exc),
            )
            raise
        finally:
            lock.release()

    def get_health(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve latest calculated health score and component breakdown for project."""
        return self.repo.get_project_health(project_id)

    def get_findings(
        self,
        project_id: str,
        category: Optional[str] = None,
        severity: Optional[str] = None,
        status: Optional[str] = None,
        priority_tier: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve stored findings filtered by category, severity, status, or priority tier."""
        return self.repo.list_findings(
            project_id=project_id,
            category=category,
            severity=severity,
            status=status,
            priority_tier=priority_tier,
        )

    def get_recommendations(self, project_id: str) -> Dict[str, Any]:
        """
        Retrieve actionable recommendations organized by priority tiers:
        FIX_FIRST, SHOULD_FIX, NICE_TO_IMPROVE, INFORMATIONAL.
        """
        open_findings = self.repo.list_findings(project_id=project_id, status="open")
        tiers: Dict[str, List[Dict[str, Any]]] = {
            PriorityTier.FIX_FIRST.value: [],
            PriorityTier.SHOULD_FIX.value: [],
            PriorityTier.NICE_TO_IMPROVE.value: [],
            PriorityTier.INFORMATIONAL.value: [],
        }

        for f in open_findings:
            tier = f.get("priority_tier", PriorityTier.SHOULD_FIX.value)
            tiers.setdefault(tier, []).append(f)

        health = self.get_health(project_id)
        return {
            "project_id": project_id,
            "overall_score": health.get("overall_score") if health else None,
            "grade": health.get("grade") if health else None,
            "summary": health.get("summary") if health else "No analysis run yet.",
            "recommendations_by_tier": tiers,
            "total_open": len(open_findings),
        }

    def get_statistics(self, project_id: str) -> Dict[str, Any]:
        """Extract high-level inventory statistics and metadata counts."""
        inventory = self.inventory_builder.build_inventory(project_id)
        return inventory.to_dict()

    def get_duplicates(self, project_id: str) -> List[Dict[str, Any]]:
        """Identify identical duplicate files grouped by content SHA-256 hash."""
        return self.repo.get_duplicate_files(project_id)

    def update_finding_status(
        self,
        finding_id: str,
        status: str,
    ) -> Optional[Dict[str, Any]]:
        """Update lifecycle status of a finding (open, acknowledged, resolved, ignored)."""
        valid_statuses = {"open", "acknowledged", "resolved", "ignored"}
        if status not in valid_statuses:
            raise ValueError(f"Invalid status '{status}'. Must be one of {valid_statuses}")
        success = self.repo.update_finding_status(finding_id, status)
        if success:
            return self.repo.get_finding(finding_id)
        return None
