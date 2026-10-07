"""
Unit tests for SVANT Health Scoring and Prioritization (Phase 4 & 5).
Validates explainable 0-100 score, component weights, severity deductions,
academic grades, and prioritization tiers.
"""

from __future__ import annotations

import pytest

from svant.core.intelligence.models import (
    Finding,
    FindingCategory,
    FindingSeverity,
    PriorityTier,
)
from svant.core.intelligence.prioritization import PrioritizationEngine
from svant.core.intelligence.scoring import HealthScorer


def test_health_scorer_clean_project():
    scorer = HealthScorer()
    health = scorer.calculate_health_score([])

    assert health.overall_score == 100
    assert health.grade == "A"
    assert health.critical_count == 0
    assert health.high_count == 0
    assert "great health" in health.summary.lower()

    # All 7 components should be 100
    for cat_name, comp in health.component_scores.items():
        assert comp.score == 100
        assert comp.findings_count == 0


def test_health_scorer_severity_deductions_and_weights():
    scorer = HealthScorer()

    # Create findings in Security (weight 0.25)
    # 1 Critical: -25 points from Security -> Security = 75
    f_crit = Finding(
        id="f1",
        project_id="proj1",
        category=FindingCategory.SECURITY,
        severity=FindingSeverity.CRITICAL,
        title="Exposed Secret",
        description="Leaked token",
        recommendation="Revoke",
    )
    health = scorer.calculate_health_score([f_crit])

    # Security comp score = 75, other 6 comps = 100
    # Expected overall = round(75*0.25 + 100*0.75) = round(18.75 + 75.0) = round(93.75) = 94
    assert health.component_scores["security"].score == 75
    assert health.overall_score == 94
    assert health.grade == "A"
    assert health.critical_count == 1


def test_health_scorer_resolved_ignored_do_not_penalize():
    scorer = HealthScorer()

    # Resolved and ignored findings
    f_resolved = Finding(
        id="f1",
        project_id="proj1",
        category=FindingCategory.SECURITY,
        severity=FindingSeverity.CRITICAL,
        title="Resolved Secret",
        description="Was resolved",
        recommendation="None",
        status="resolved",
    )
    f_ignored = Finding(
        id="f2",
        project_id="proj1",
        category=FindingCategory.QUALITY,
        severity=FindingSeverity.HIGH,
        title="Ignored Monolith",
        description="Ignored",
        recommendation="None",
        status="ignored",
    )

    health = scorer.calculate_health_score([f_resolved, f_ignored])
    assert health.overall_score == 100
    assert health.grade == "A"


def test_health_scorer_grade_brackets():
    scorer = HealthScorer()
    assert scorer._score_to_grade(95) == "A"
    assert scorer._score_to_grade(90) == "A"
    assert scorer._score_to_grade(85) == "B"
    assert scorer._score_to_grade(80) == "B"
    assert scorer._score_to_grade(75) == "C"
    assert scorer._score_to_grade(70) == "C"
    assert scorer._score_to_grade(65) == "D"
    assert scorer._score_to_grade(60) == "D"
    assert scorer._score_to_grade(55) == "F"
    assert scorer._score_to_grade(0) == "F"


def test_prioritization_engine():
    engine = PrioritizationEngine()

    f1 = Finding(
        id="1",
        project_id="p1",
        category=FindingCategory.SECURITY,
        severity=FindingSeverity.CRITICAL,
        title="Critical AWS Secret",
        description="",
        recommendation="",
    )
    f2 = Finding(
        id="2",
        project_id="p1",
        category=FindingCategory.TESTING,
        severity=FindingSeverity.MEDIUM,
        title="No Test Suite",
        description="",
        recommendation="",
    )
    f3 = Finding(
        id="3",
        project_id="p1",
        category=FindingCategory.HYGIENE,
        severity=FindingSeverity.LOW,
        title="Duplicate File Clutter",
        description="",
        recommendation="",
    )
    f4 = Finding(
        id="4",
        project_id="p1",
        category=FindingCategory.STRUCTURE,
        severity=FindingSeverity.INFO,
        title="Deep Directory Structure",
        description="",
        recommendation="",
    )

    prioritized = engine.prioritize_findings([f4, f3, f2, f1])

    # Ordered: FIX_FIRST -> SHOULD_FIX -> NICE_TO_IMPROVE -> INFORMATIONAL
    assert prioritized[0].priority_tier == PriorityTier.FIX_FIRST
    assert prioritized[0].id == "1"

    assert prioritized[1].priority_tier == PriorityTier.SHOULD_FIX
    assert prioritized[1].id == "2"

    assert prioritized[2].priority_tier == PriorityTier.NICE_TO_IMPROVE
    assert prioritized[2].id == "3"

    assert prioritized[3].priority_tier == PriorityTier.INFORMATIONAL
    assert prioritized[3].id == "4"

    # Group by tier
    grouped = engine.group_by_tier(prioritized)
    assert len(grouped["fix_first"]) == 1
    assert len(grouped["should_fix"]) == 1
    assert len(grouped["nice_to_improve"]) == 1
    assert len(grouped["informational"]) == 1
