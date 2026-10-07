"""
RAG Context Assembler for SVANT Phase 3.
Selects, deduplicates, prioritizes, and bounds retrieved document chunks
into structured, traceable context for AI generation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Set

from svant.config import settings
from svant.logger import get_logger

logger = get_logger("svant.core.rag.context")


@dataclass
class ContextItem:
    """Represents a bounded, traceable piece of project evidence."""

    file_id: str
    chunk_id: Optional[str]
    filename: str
    relative_path: str
    project_id: str
    chunk_index: int
    content: str
    relevance_score: float
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    section: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def citation_label(self) -> str:
        """Formatted location label (e.g. 'Lines 12–35' or 'Section ## Overview' or 'Chunk 2')."""
        if self.line_start is not None and self.line_end is not None:
            return f"Lines {self.line_start}–{self.line_end}"
        if self.section:
            return f"Section {self.section}"
        if self.chunk_index is not None:
            return f"Chunk {self.chunk_index + 1}"
        return "Excerpt"


class ContextAssembler:
    """Selects and formats top search hits into a structured context window."""

    def __init__(
        self,
        top_k: Optional[int] = None,
        max_context_chars: Optional[int] = None,
    ) -> None:
        self.top_k = top_k or getattr(settings, "rag_top_k", 8)
        self.max_context_chars = max_context_chars or getattr(settings, "rag_max_context_chars", 30000)

    def assemble(
        self,
        search_hits: List[Dict[str, Any]],
        project_id: Optional[str] = None,
    ) -> List[ContextItem]:
        """
        Deduplicate and bound search hits into an ordered list of ContextItems.
        """
        if not search_hits:
            return []

        # Sort by relevance score descending
        sorted_hits = sorted(search_hits, key=lambda x: x.get("score", 0.0), reverse=True)

        items: List[ContextItem] = []
        seen_keys: Set[str] = set()
        accumulated_chars = 0

        for hit in sorted_hits:
            if len(items) >= self.top_k:
                break

            # Deduplication key: chunk_id or (file_id + snippet)
            cid = hit.get("chunk_id")
            fid = hit.get("file_id", "")
            snippet = hit.get("snippet", "")
            dedup_key = cid if cid else f"{fid}:{snippet[:100]}"

            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)

            # Metadata parsing
            meta = hit.get("metadata") or {}
            line_start = meta.get("start_line")
            line_end = meta.get("end_line")
            section = meta.get("section")
            chunk_idx = meta.get("chunk_index", 0)

            content = snippet.strip()
            item_len = len(content)

            # Enforce max context character budget
            if accumulated_chars + item_len > self.max_context_chars:
                remaining_budget = self.max_context_chars - accumulated_chars
                if remaining_budget < 200:
                    break
                # Truncate content to fit remaining budget
                content = content[:remaining_budget] + "\n... [truncated to fit context budget]"
                item_len = len(content)

            item = ContextItem(
                file_id=fid,
                chunk_id=cid,
                filename=hit.get("filename", "unknown"),
                relative_path=hit.get("relative_path", "unknown"),
                project_id=hit.get("project_id", project_id or ""),
                chunk_index=chunk_idx,
                content=content,
                relevance_score=float(hit.get("score", 0.0)),
                line_start=line_start,
                line_end=line_end,
                section=section,
            )
            items.append(item)
            accumulated_chars += item_len

        logger.debug(f"Assembled {len(items)} context items totaling {accumulated_chars} characters.")
        return items

    def format_context_for_prompt(self, context_items: List[ContextItem]) -> str:
        """
        Convert structured context items into a clean textual representation for LLM prompts.
        """
        if not context_items:
            return "No relevant project files found."

        parts = []
        for idx, item in enumerate(context_items, start=1):
            header = f"--- [Source {idx}: {item.relative_path} ({item.citation_label}, Relevance: {item.relevance_score:.2f})] ---"
            parts.append(f"{header}\n{item.content}\n")

        return "\n".join(parts)
