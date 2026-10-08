"""
SVANT Project Intelligence Module (Phase 4 & 5).
Comprehensive codebase understanding, health scoring, security scanning,
and grounded recommendations.
"""

from svant.core.intelligence.analyzer import ProjectIntelligenceEngine
from svant.core.intelligence.dependencies import DependencyAnalyzer
from svant.core.intelligence.documentation import DocumentationAnalyzer
from svant.core.intelligence.duplicates import DuplicateDetector
from svant.core.intelligence.hygiene import HygieneAnalyzer
from svant.core.intelligence.inventory import ProjectInventoryBuilder
from svant.core.intelligence.models import (
    ComponentScore,
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

__all__ = [
    "ProjectIntelligenceEngine",
    "DuplicateDetector",
    "ProjectInventoryBuilder",
    "ProjectStructureAnalyzer",
    "SecurityAnalyzer",
    "DependencyAnalyzer",
    "TestingAnalyzer",
    "DocumentationAnalyzer",
    "HygieneAnalyzer",
    "QualityAnalyzer",
    "HealthScorer",
    "PrioritizationEngine",
    "Finding",
    "FindingCategory",
    "FindingSeverity",
    "PriorityTier",
    "ComponentScore",
    "HealthScore",
    "ProjectInventory",
    "StructureAnalysis",
]
