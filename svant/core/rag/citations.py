"""
Citation generator for SVANT Phase 3 RAG.
Converts context evidence into traceable file references and line/section citations.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

from svant.core.rag.context import ContextItem


@dataclass
class Citation:
    """Traceable citation pointing to the exact local file location of evidence."""

    file_id: str
    filename: str
    relative_path: str
    location: str  # e.g. "Lines 42–67", "Section ## Auth", "Chunk 2"
    relevance_score: float
    snippet_preview: str
    chunk_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CitationGenerator:
    """Extracts clean, honest source citations from assembled context items."""

    @staticmethod
    def generate(context_items: List[ContextItem]) -> List[Citation]:
        """Convert bounded context items into user-facing citations."""
        citations: List[Citation] = []
        seen = set()

        for item in context_items:
            key = f"{item.file_id}:{item.citation_label}"
            if key in seen:
                continue
            seen.add(key)

            preview = item.content.replace("\n", " ").strip()
            if len(preview) > 160:
                preview = preview[:160] + "..."

            cit = Citation(
                file_id=item.file_id,
                filename=item.filename,
                relative_path=item.relative_path,
                location=item.citation_label,
                relevance_score=round(item.relevance_score, 4),
                snippet_preview=preview,
                chunk_id=item.chunk_id,
            )
            citations.append(cit)

        return citations
