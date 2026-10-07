"""
Explainable SVANT Health Scoring System (Phase 4 & 5).
Calculates an explainable 0-100 score with explicit weights and rationale across 7 components:
Security (25%), Quality (15%), Testing (15%), Documentation (15%),
Dependencies (10%), Hygiene (10%), Structure (10%).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Tuple

from svant.core.intelligence.models import (
    ComponentScore,
    Finding,
    FindingCategory,
    FindingSeverity,
    HealthScore,
)
from svant.logger import get_logger

logger = get_logger("svant.core.intelligence.scoring")

# Explicit component weights totaling 1.0 (100%)
COMPONENT_WEIGHTS: Dict[FindingCategory, float] = {
    FindingCategory.SECURITY: 0.25,
    FindingCategory.QUALITY: 0.15,
    FindingCategory.TESTING: 0.15,
    FindingCategory.DOCUMENTATION: 0.15,
    FindingCategory.DEPENDENCIES: 0.10,
    FindingCategory.HYGIENE: 0.10,
    FindingCategory.STRUCTURE: 0.10,
}

# Severity deduction values per finding
SEVERITY_DEDUCTIONS: Dict[FindingSeverity, int] = {
    FindingSeverity.CRITICAL: 25,
    FindingSeverity.HIGH: 15,
    FindingSeverity.MEDIUM: 8,
    FindingSeverity.LOW: 3,
    FindingSeverity.INFO: 0,
}


class HealthScorer:
    """Calculates weighted, transparent project health scores and component grades."""

    def calculate_health_score(self, findings: List[Finding]) -> HealthScore:
        """
        Compute overall project health score and detailed component breakdown.
        Filters by open/acknowledged findings (resolved and ignored do not penalize).
        """
        # Active findings that contribute to score deductions
        active_findings = [f for f in findings if f.status not in ("resolved", "ignored")]

        # Group findings by category
        findings_by_cat: Dict[FindingCategory, List[Finding]] = {cat: [] for cat in COMPONENT_WEIGHTS}
        for f in active_findings:
            # Map MAINTAINABILITY to QUALITY if present
            cat = f.category
            if cat == FindingCategory.MAINTAINABILITY:
                cat = FindingCategory.QUALITY
            if cat in findings_by_cat:
                findings_by_cat[cat].append(f)
            else:
                findings_by_cat.setdefault(FindingCategory.QUALITY, []).append(f)

        # Count severities across all active findings
        crit_count = sum(1 for f in active_findings if f.severity == FindingSeverity.CRITICAL)
        high_count = sum(1 for f in active_findings if f.severity == FindingSeverity.HIGH)
        med_count = sum(1 for f in active_findings if f.severity == FindingSeverity.MEDIUM)
        low_count = sum(1 for f in active_findings if f.severity == FindingSeverity.LOW)
        info_count = sum(1 for f in active_findings if f.severity == FindingSeverity.INFO)

        component_scores: Dict[str, ComponentScore] = {}
        weighted_sum = 0.0

        for cat, weight in COMPONENT_WEIGHTS.items():
            cat_findings = findings_by_cat[cat]
            score, rationale = self._score_component(cat, cat_findings)
            comp_score = ComponentScore(
                category=cat,
                score=score,
                weight=weight,
                rationale=rationale,
                findings_count=len(cat_findings),
                max_score=100,
            )
            component_scores[cat.value] = comp_score
            weighted_sum += (score * weight)

        overall_score = max(0, min(100, int(round(weighted_sum))))
        grade = self._score_to_grade(overall_score)
        summary = self._generate_summary(overall_score, grade, component_scores, crit_count, high_count, med_count)

        return HealthScore(
            overall_score=overall_score,
            grade=grade,
            component_scores=component_scores,
            summary=summary,
            critical_count=crit_count,
            high_count=high_count,
            medium_count=med_count,
            low_count=low_count,
            info_count=info_count,
            analyzed_at=datetime.now(timezone.utc).isoformat(),
        )

    def _score_component(
        self,
        category: FindingCategory,
        findings: List[Finding],
    ) -> Tuple[int, str]:
        """Calculate single component score (0-100) and explainable rationale."""
        if not findings:
            return 100, f"Excellent: No {category.value} issues detected."

        deductions = 0
        crit = 0
        high = 0
        med = 0
        low = 0

        for f in findings:
            ded = SEVERITY_DEDUCTIONS.get(f.severity, 0)
            deductions += ded
            if f.severity == FindingSeverity.CRITICAL:
                crit += 1
            elif f.severity == FindingSeverity.HIGH:
                high += 1
            elif f.severity == FindingSeverity.MEDIUM:
                med += 1
            elif f.severity == FindingSeverity.LOW:
                low += 1

        final_score = max(0, min(100, 100 - deductions))

        # Build clear rationale
        reasons: List[str] = []
        if crit > 0:
            reasons.append(f"{crit} critical")
        if high > 0:
            reasons.append(f"{high} high")
        if med > 0:
            reasons.append(f"{med} medium")
        if low > 0:
            reasons.append(f"{low} low")

        if reasons:
            reasons_str = ", ".join(reasons)
            if final_score >= 80:
                rationale = f"Good ({final_score}/100): Minor deductions for {reasons_str} issues."
            elif final_score >= 60:
                rationale = f"Moderate ({final_score}/100): Deductions for {reasons_str} issues."
            else:
                rationale = f"Needs Attention ({final_score}/100): Significant deductions from {reasons_str} issues."
        else:
            rationale = f"Perfect ({final_score}/100): Only informational findings."

        return final_score, rationale

    def _score_to_grade(self, score: int) -> str:
        """Convert a 0-100 score to an academic grade."""
        if score >= 90:
            return "A"
        elif score >= 80:
            return "B"
        elif score >= 70:
            return "C"
        elif score >= 60:
            return "D"
        return "F"

    def _generate_summary(
        self,
        score: int,
        grade: str,
        components: Dict[str, ComponentScore],
        crit_count: int,
        high_count: int,
        med_count: int,
    ) -> str:
        """Construct an explainable, human-readable summary of project health."""
        # Find weakest component(s)
        sorted_comps = sorted(components.values(), key=lambda c: c.score)
        weakest = [c for c in sorted_comps if c.score < 80]

        parts: List[str] = [f"Grade {grade} ({score}/100)."]

        if crit_count > 0 or high_count > 0:
            parts.append(
                f"Requires immediate attention: {crit_count} critical and {high_count} high severity findings identified."
            )
        elif med_count > 0:
            parts.append(f"Identified {med_count} medium priority improvements to address.")
        else:
            parts.append("Project is in great health with no severe issues detected.")

        if weakest:
            weak_names = ", ".join(c.category.value.title() for c in weakest[:2])
            parts.append(f"Key areas for improvement: {weak_names}.")

        return " ".join(parts)
