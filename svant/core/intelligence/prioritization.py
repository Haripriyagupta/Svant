"""
Prioritization Engine for SVANT Project Intelligence (Phase 4 & 5).
Categorizes findings into actionable priority tiers with explainable rationale:
- FIX FIRST: Immediate action required (critical/high security, exposed keys, corrupted lockfiles)
- SHOULD FIX: Important improvements (missing tests, unpinned deps, monolithic files, missing docs)
- NICE TO IMPROVE: Minor hygiene, duplicate cleanup, leftover debug logs
- INFORMATIONAL: Metrics, large files, informational structural insights
"""

from __future__ import annotations

from typing import Dict, List

from svant.core.intelligence.models import (
    Finding,
    FindingCategory,
    FindingSeverity,
    PriorityTier,
)
from svant.logger import get_logger

logger = get_logger("svant.core.intelligence.prioritization")

TIER_ORDER: Dict[PriorityTier, int] = {
    PriorityTier.FIX_FIRST: 1,
    PriorityTier.SHOULD_FIX: 2,
    PriorityTier.NICE_TO_IMPROVE: 3,
    PriorityTier.INFORMATIONAL: 4,
}

SEVERITY_ORDER: Dict[FindingSeverity, int] = {
    FindingSeverity.CRITICAL: 1,
    FindingSeverity.HIGH: 2,
    FindingSeverity.MEDIUM: 3,
    FindingSeverity.LOW: 4,
    FindingSeverity.INFO: 5,
}


class PrioritizationEngine:
    """Assigns priority tiers and sorts recommendations by urgency and impact."""

    def assign_priority(self, finding: Finding) -> PriorityTier:
        """Assign appropriate PriorityTier based on severity and category heuristics."""
        # 1. Any critical or high security finding is Fix First
        if finding.category == FindingCategory.SECURITY and finding.severity in (
            FindingSeverity.CRITICAL,
            FindingSeverity.HIGH,
        ):
            return PriorityTier.FIX_FIRST

        # Any critical finding in any category is Fix First
        if finding.severity == FindingSeverity.CRITICAL:
            return PriorityTier.FIX_FIRST

        # High severity dependency issues (e.g. missing lockfile or duplicate declarations)
        if finding.severity == FindingSeverity.HIGH:
            return PriorityTier.FIX_FIRST

        # Medium severity issues (missing docs, no tests, unpinned deps, monoliths) -> Should Fix
        if finding.severity == FindingSeverity.MEDIUM:
            return PriorityTier.SHOULD_FIX

        # Low severity -> Nice to improve
        if finding.severity == FindingSeverity.LOW:
            return PriorityTier.NICE_TO_IMPROVE

        # Informational
        return PriorityTier.INFORMATIONAL

    def prioritize_findings(self, findings: List[Finding]) -> List[Finding]:
        """
        Assigns priority tier to each finding and returns findings sorted by urgency:
        Tier (FIX_FIRST -> SHOULD_FIX -> NICE_TO_IMPROVE -> INFORMATIONAL),
        then Severity (CRITICAL -> HIGH -> MEDIUM -> LOW -> INFO),
        then alphabetical by title.
        """
        for f in findings:
            f.priority_tier = self.assign_priority(f)

        return sorted(
            findings,
            key=lambda x: (
                TIER_ORDER.get(x.priority_tier, 99),
                SEVERITY_ORDER.get(x.severity, 99),
                x.title.lower(),
            ),
        )

    def group_by_tier(self, findings: List[Finding]) -> Dict[str, List[Finding]]:
        """Group prioritized findings by their priority tier name."""
        prioritized = self.prioritize_findings(findings)
        grouped: Dict[str, List[Finding]] = {
            PriorityTier.FIX_FIRST.value: [],
            PriorityTier.SHOULD_FIX.value: [],
            PriorityTier.NICE_TO_IMPROVE.value: [],
            PriorityTier.INFORMATIONAL.value: [],
        }
        for f in prioritized:
            tier_val = f.priority_tier.value if isinstance(f.priority_tier, PriorityTier) else str(f.priority_tier)
            grouped.setdefault(tier_val, []).append(f)
        return grouped
