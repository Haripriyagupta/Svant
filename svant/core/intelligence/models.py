"""
Data models and enumeration types for SVANT Project Intelligence (Phase 4 & 5).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid


class FindingSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class FindingCategory(str, Enum):
    SECURITY = "security"
    QUALITY = "quality"
    TESTING = "testing"
    DOCUMENTATION = "documentation"
    DEPENDENCIES = "dependencies"
    HYGIENE = "hygiene"
    STRUCTURE = "structure"
    MAINTAINABILITY = "maintainability"


class PriorityTier(str, Enum):
    FIX_FIRST = "fix_first"
    SHOULD_FIX = "should_fix"
    NICE_TO_IMPROVE = "nice_to_improve"
    INFORMATIONAL = "informational"


@dataclass
class Finding:
    """Represents a normalized, evidence-grounded project intelligence finding."""

    id: str
    project_id: str
    category: FindingCategory
    severity: FindingSeverity
    title: str
    description: str
    recommendation: str
    priority_tier: PriorityTier = PriorityTier.SHOULD_FIX
    file_id: Optional[str] = None
    relative_path: Optional[str] = None
    location: Optional[str] = None
    evidence: Optional[str] = None
    confidence: float = 1.0
    fingerprint: str = ""
    status: str = "open"
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            self.id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now
        if not self.fingerprint:
            # Deterministic fingerprint to deduplicate findings across re-analyses
            path_part = self.relative_path or ""
            cat_val = self.category.value if isinstance(self.category, FindingCategory) else str(self.category)
            self.fingerprint = f"{self.project_id}:{cat_val}:{self.title.strip()}:{path_part.strip()}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "category": self.category.value if isinstance(self.category, FindingCategory) else str(self.category),
            "severity": self.severity.value if isinstance(self.severity, FindingSeverity) else str(self.severity),
            "priority_tier": self.priority_tier.value if isinstance(self.priority_tier, PriorityTier) else str(self.priority_tier),
            "title": self.title,
            "description": self.description,
            "recommendation": self.recommendation,
            "file_id": self.file_id,
            "relative_path": self.relative_path,
            "location": self.location,
            "evidence": self.evidence,
            "confidence": self.confidence,
            "fingerprint": self.fingerprint,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class ComponentScore:
    """Explainable category score contributing to the overall SVANT Health Score."""

    category: FindingCategory
    score: int  # 0 to 100
    weight: float  # weight in overall score
    rationale: str
    findings_count: int = 0
    max_score: int = 100

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category.value if isinstance(self.category, FindingCategory) else str(self.category),
            "score": self.score,
            "weight": self.weight,
            "rationale": self.rationale,
            "findings_count": self.findings_count,
            "max_score": self.max_score,
        }


@dataclass
class HealthScore:
    """Overall SVANT Health Score with explainable component weights and breakdown."""

    overall_score: int  # 0 to 100
    grade: str  # A, B, C, D, F
    component_scores: Dict[str, ComponentScore]
    summary: str
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    info_count: int = 0
    analyzed_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_score": self.overall_score,
            "grade": self.grade,
            "component_scores": {k: v.to_dict() for k, v in self.component_scores.items()},
            "summary": self.summary,
            "critical_count": self.critical_count,
            "high_count": self.high_count,
            "medium_count": self.medium_count,
            "low_count": self.low_count,
            "info_count": self.info_count,
            "analyzed_at": self.analyzed_at,
        }


@dataclass
class ProjectInventory:
    """Comprehensive inventory of scanned project files, metrics, and ecosystems."""

    total_files: int = 0
    total_size_bytes: int = 0
    source_files: int = 0
    document_files: int = 0
    config_files: int = 0
    data_files: int = 0
    binary_files: int = 0
    other_files: int = 0
    category_counts: Dict[str, int] = field(default_factory=dict)
    extension_counts: Dict[str, int] = field(default_factory=dict)
    languages: Dict[str, int] = field(default_factory=dict)
    largest_files: List[Dict[str, Any]] = field(default_factory=list)
    oldest_files: List[Dict[str, Any]] = field(default_factory=list)
    newest_files: List[Dict[str, Any]] = field(default_factory=list)
    total_dirs: int = 0
    deep_dirs: List[str] = field(default_factory=list)
    test_files: List[Dict[str, Any]] = field(default_factory=list)
    doc_files: List[Dict[str, Any]] = field(default_factory=list)
    manifest_files: List[Dict[str, Any]] = field(default_factory=list)
    lock_files: List[Dict[str, Any]] = field(default_factory=list)
    build_artifact_files: List[Dict[str, Any]] = field(default_factory=list)
    unextracted_files: int = 0
    indexed_files: int = 0
    chunk_count: int = 0
    vector_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class StructureAnalysis:
    """Structural breakdown and framework ecosystem detection for a project."""

    primary_ecosystem: str = "generic"
    detected_ecosystems: List[str] = field(default_factory=list)
    source_roots: List[str] = field(default_factory=list)
    test_roots: List[str] = field(default_factory=list)
    doc_roots: List[str] = field(default_factory=list)
    config_roots: List[str] = field(default_factory=list)
    build_dirs: List[str] = field(default_factory=list)
    virtual_env_dirs: List[str] = field(default_factory=list)
    cache_dirs: List[str] = field(default_factory=list)
    max_depth: int = 0
    structure_issues: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
