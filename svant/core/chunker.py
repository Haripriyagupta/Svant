"""
Intelligent text chunking engine for SVANT Phase 2.
Supports specialized chunking strategies for source code, markdown,
plain text, CSV, documents, and configuration files.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from svant.config import settings
from svant.logger import get_logger

logger = get_logger("svant.core.chunker")


@dataclass
class TextChunk:
    """Represents a discrete semantic chunk of a file."""

    chunk_id: str
    project_id: str
    file_id: str
    relative_path: str
    filename: str
    chunk_index: int
    text: str
    char_count: int
    word_count: int
    content_type: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TextChunker:
    """Multi-strategy chunker preserving structural boundaries and metadata."""

    def __init__(
        self,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
        min_chunk_chars: int = 30,
    ) -> None:
        self.chunk_size = chunk_size or getattr(settings, "chunk_size", 500)
        self.chunk_overlap = chunk_overlap or getattr(settings, "chunk_overlap", 50)
        self.min_chunk_chars = min_chunk_chars

    def chunk_document(
        self,
        project_id: str,
        file_id: str,
        relative_path: str,
        filename: str,
        text: str,
        category: str = "document",
    ) -> List[TextChunk]:
        """
        Split document text into chunks based on file extension and category.
        """
        if not text or not text.strip():
            return []

        clean_text = text.strip()
        lower_name = filename.lower()
        ext = "." + lower_name.split(".")[-1] if "." in lower_name else ""

        # Choose chunking strategy
        if ext == ".md" or ext == ".markdown":
            raw_chunks = self._chunk_markdown(clean_text)
        elif category == "source" or ext in {
            ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".c", ".cpp",
            ".cs", ".go", ".rs", ".rb", ".php", ".sh", ".sql", ".html", ".css",
        }:
            raw_chunks = self._chunk_source_code(clean_text, ext)
        elif ext in {".csv", ".tsv"}:
            raw_chunks = self._chunk_csv(clean_text)
        elif category == "config" or ext in {".json", ".yaml", ".yml", ".toml", ".ini", ".env", ".xml"}:
            raw_chunks = self._chunk_config(clean_text, ext)
        else:
            # Plain text, PDF, DOCX, etc.
            raw_chunks = self._chunk_prose(clean_text)

        # Post-process: filter out degenerate chunks, attach IDs and indices
        final_chunks: List[TextChunk] = []
        chunk_index = 0

        for chunk_data in raw_chunks:
            chunk_str = chunk_data["text"].strip()
            # If text is too small and we already have chunks, skip unless it's the only one
            if len(chunk_str) < self.min_chunk_chars and raw_chunks and len(raw_chunks) > 1:
                continue

            chunk_meta = chunk_data.get("metadata", {})
            chunk_meta["relative_path"] = relative_path
            chunk_meta["filename"] = filename

            chunk_obj = TextChunk(
                chunk_id=str(uuid.uuid4()),
                project_id=project_id,
                file_id=file_id,
                relative_path=relative_path,
                filename=filename,
                chunk_index=chunk_index,
                text=chunk_str,
                char_count=len(chunk_str),
                word_count=len(chunk_str.split()),
                content_type=category,
                metadata=chunk_meta,
            )
            final_chunks.append(chunk_obj)
            chunk_index += 1

        # If everything was filtered out due to min_chunk_chars, keep the whole text as single chunk
        if not final_chunks and clean_text:
            final_chunks.append(
                TextChunk(
                    chunk_id=str(uuid.uuid4()),
                    project_id=project_id,
                    file_id=file_id,
                    relative_path=relative_path,
                    filename=filename,
                    chunk_index=0,
                    text=clean_text,
                    char_count=len(clean_text),
                    word_count=len(clean_text.split()),
                    content_type=category,
                    metadata={"strategy": "fallback_single"},
                )
            )

        return final_chunks

    # -------------------------------------------------------------------------
    # STRATEGY 1: MARKDOWN (Heading & Section Aware)
    # -------------------------------------------------------------------------
    def _chunk_markdown(self, text: str) -> List[Dict[str, Any]]:
        """Split markdown text by headers (#, ##, ###), keeping header context."""
        lines = text.splitlines(keepends=True)
        sections: List[Dict[str, Any]] = []
        current_header = "Document Start"
        current_lines: List[str] = []

        header_pattern = re.compile(r"^(#{1,6})\s+(.+)$")

        for line in lines:
            match = header_pattern.match(line.strip())
            if match:
                if current_lines:
                    sec_text = "".join(current_lines).strip()
                    if sec_text:
                        sections.append({"header": current_header, "text": sec_text})
                    current_lines = []
                current_header = line.strip()
                current_lines.append(line)
            else:
                current_lines.append(line)

        if current_lines:
            sec_text = "".join(current_lines).strip()
            if sec_text:
                sections.append({"header": current_header, "text": sec_text})

        chunks: List[Dict[str, Any]] = []
        for sec in sections:
            sec_header = sec["header"]
            sec_text = sec["text"]

            if len(sec_text) <= self.chunk_size:
                chunks.append({
                    "text": sec_text,
                    "metadata": {"strategy": "markdown_section", "section": sec_header},
                })
            else:
                # Sub-split long section by paragraphs
                sub_chunks = self._sliding_window_split(sec_text, self.chunk_size, self.chunk_overlap)
                for sc in sub_chunks:
                    # Prepend section header to sub-chunks if not present
                    chunk_content = sc
                    if not chunk_content.startswith(sec_header) and sec_header != "Document Start":
                        chunk_content = f"[{sec_header}]\n{chunk_content}"
                    chunks.append({
                        "text": chunk_content,
                        "metadata": {"strategy": "markdown_sub_section", "section": sec_header},
                    })

        return chunks

    # -------------------------------------------------------------------------
    # STRATEGY 2: SOURCE CODE (Function, Class & Block Aware)
    # -------------------------------------------------------------------------
    def _chunk_source_code(self, text: str, ext: str) -> List[Dict[str, Any]]:
        """Split source code along function/class declarations or line blocks."""
        lines = text.splitlines(keepends=True)
        if len(text) <= self.chunk_size:
            return [{
                "text": text,
                "metadata": {"strategy": "code_single_block", "ext": ext, "start_line": 1, "end_line": len(lines)},
            }]

        # Regex heuristics for code block headers
        block_pattern = re.compile(
            r"^(class\s+|def\s+|async\s+def\s+|function\s+|export\s+|pub\s+fn\s+|impl\s+|fn\s+|struct\s+|interface\s+)"
        )

        blocks: List[Dict[str, Any]] = []
        current_block: List[str] = []
        start_line = 1

        for idx, line in enumerate(lines, start=1):
            is_new_block = bool(block_pattern.match(line.lstrip())) and len(current_block) > 0

            # If new top-level definition or accumulated block exceeded chunk size
            current_len = sum(len(l) for l in current_block)
            if is_new_block and current_len >= self.chunk_size // 2:
                block_text = "".join(current_block).strip()
                if block_text:
                    blocks.append({
                        "text": block_text,
                        "metadata": {
                            "strategy": "code_definition_block",
                            "ext": ext,
                            "start_line": start_line,
                            "end_line": idx - 1,
                        },
                    })
                current_block = [line]
                start_line = idx
            else:
                current_block.append(line)

        if current_block:
            block_text = "".join(current_block).strip()
            if block_text:
                blocks.append({
                    "text": block_text,
                    "metadata": {
                        "strategy": "code_definition_block",
                        "ext": ext,
                        "start_line": start_line,
                        "end_line": len(lines),
                    },
                })

        # Check if any individual code block is still too large
        chunks: List[Dict[str, Any]] = []
        for blk in blocks:
            if len(blk["text"]) <= self.chunk_size * 1.5:
                chunks.append(blk)
            else:
                # Sub-split large code block via line window
                sub_lines = blk["text"].splitlines(keepends=True)
                accum: List[str] = []
                cur_start = blk["metadata"].get("start_line", 1)

                for l in sub_lines:
                    accum.append(l)
                    if sum(len(x) for x in accum) >= self.chunk_size:
                        sub_text = "".join(accum).strip()
                        chunks.append({
                            "text": sub_text,
                            "metadata": {
                                "strategy": "code_line_window",
                                "ext": ext,
                                "start_line": cur_start,
                            },
                        })
                        # Overlap: keep last few lines
                        overlap_lines: List[str] = []
                        overlap_chars = 0
                        for ol in reversed(accum):
                            if overlap_chars + len(ol) <= self.chunk_overlap:
                                overlap_lines.insert(0, ol)
                                overlap_chars += len(ol)
                            else:
                                break
                        accum = overlap_lines

                if accum:
                    sub_text = "".join(accum).strip()
                    if sub_text:
                        chunks.append({
                            "text": sub_text,
                            "metadata": {
                                "strategy": "code_line_window",
                                "ext": ext,
                                "start_line": cur_start,
                            },
                        })

        return chunks

    # -------------------------------------------------------------------------
    # STRATEGY 3: PROSE & GENERAL TEXT (Paragraph & Sentence Aware)
    # -------------------------------------------------------------------------
    def _chunk_prose(self, text: str) -> List[Dict[str, Any]]:
        """Split plain text or document prose by paragraphs and sentence boundaries."""
        if len(text) <= self.chunk_size:
            return [{"text": text, "metadata": {"strategy": "prose_single"}}]

        paragraphs = [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]
        chunks: List[Dict[str, Any]] = []
        current_chunk_parts: List[str] = []
        current_length = 0

        for para in paragraphs:
            para_len = len(para)

            # If a single paragraph is larger than chunk_size, split by sentences
            if para_len > self.chunk_size:
                if current_chunk_parts:
                    joined = "\n\n".join(current_chunk_parts)
                    chunks.append({"text": joined, "metadata": {"strategy": "prose_paragraph"}})
                    current_chunk_parts = []
                    current_length = 0

                sentences = re.split(r"(?<=[.!?])\s+", para)
                s_parts: List[str] = []
                s_len = 0
                for s in sentences:
                    if s_len + len(s) > self.chunk_size and s_parts:
                        chunks.append({"text": " ".join(s_parts), "metadata": {"strategy": "prose_sentence"}})
                        # Overlap with the last sentence
                        s_parts = [s_parts[-1], s] if len(s_parts[-1]) <= self.chunk_overlap else [s]
                        s_len = sum(len(x) for x in s_parts)
                    else:
                        s_parts.append(s)
                        s_len += len(s)
                if s_parts:
                    chunks.append({"text": " ".join(s_parts), "metadata": {"strategy": "prose_sentence"}})
                continue

            if current_length + para_len + 2 > self.chunk_size and current_chunk_parts:
                joined = "\n\n".join(current_chunk_parts)
                chunks.append({"text": joined, "metadata": {"strategy": "prose_paragraph"}})
                # Overlap: keep the last paragraph if small enough
                if len(current_chunk_parts[-1]) <= self.chunk_overlap:
                    current_chunk_parts = [current_chunk_parts[-1], para]
                    current_length = sum(len(p) for p in current_chunk_parts) + 2
                else:
                    current_chunk_parts = [para]
                    current_length = para_len
            else:
                current_chunk_parts.append(para)
                current_length += para_len + 2

        if current_chunk_parts:
            joined = "\n\n".join(current_chunk_parts)
            chunks.append({"text": joined, "metadata": {"strategy": "prose_paragraph"}})

        return chunks

    # -------------------------------------------------------------------------
    # STRATEGY 4: CSV / TSV (Header Preservation)
    # -------------------------------------------------------------------------
    def _chunk_csv(self, text: str) -> List[Dict[str, Any]]:
        """Split CSV data into chunks while preserving the table header in each chunk."""
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return []

        header = lines[0]
        data_rows = lines[1:]

        if not data_rows or len(text) <= self.chunk_size:
            return [{"text": text, "metadata": {"strategy": "csv_table", "header": header}}]

        chunks: List[Dict[str, Any]] = []
        current_rows: List[str] = []
        current_len = len(header) + 1

        for row in data_rows:
            row_len = len(row) + 1
            if current_len + row_len > self.chunk_size and current_rows:
                chunk_text = f"Header: {header}\n" + "\n".join(current_rows)
                chunks.append({
                    "text": chunk_text,
                    "metadata": {"strategy": "csv_table_slice", "header": header, "rows": len(current_rows)},
                })
                current_rows = [row]
                current_len = len(header) + 1 + row_len
            else:
                current_rows.append(row)
                current_len += row_len

        if current_rows:
            chunk_text = f"Header: {header}\n" + "\n".join(current_rows)
            chunks.append({
                "text": chunk_text,
                "metadata": {"strategy": "csv_table_slice", "header": header, "rows": len(current_rows)},
            })

        return chunks

    # -------------------------------------------------------------------------
    # STRATEGY 5: CONFIGURATION FILES (JSON, YAML, INI, TOML)
    # -------------------------------------------------------------------------
    def _chunk_config(self, text: str, ext: str) -> List[Dict[str, Any]]:
        """Split configuration files respecting section headers or key blocks."""
        if len(text) <= self.chunk_size:
            return [{"text": text, "metadata": {"strategy": "config_single", "ext": ext}}]

        # Check for INI / TOML style sections [section_name]
        lines = text.splitlines(keepends=True)
        section_pattern = re.compile(r"^\[([a-zA-Z0-9_.-]+)\]")
        sections: List[Dict[str, Any]] = []
        current_sec = "root"
        current_lines: List[str] = []

        for line in lines:
            match = section_pattern.match(line.strip())
            if match and current_lines:
                sec_text = "".join(current_lines).strip()
                if sec_text:
                    sections.append({"section": current_sec, "text": sec_text})
                current_sec = match.group(1)
                current_lines = [line]
            else:
                current_lines.append(line)

        if current_lines:
            sec_text = "".join(current_lines).strip()
            if sec_text:
                sections.append({"section": current_sec, "text": sec_text})

        if len(sections) > 1:
            chunks: List[Dict[str, Any]] = []
            for sec in sections:
                if len(sec["text"]) <= self.chunk_size:
                    chunks.append({"text": sec["text"], "metadata": {"strategy": "config_section", "section": sec["section"]}})
                else:
                    sub_chunks = self._sliding_window_split(sec["text"], self.chunk_size, self.chunk_overlap)
                    for sc in sub_chunks:
                        chunks.append({"text": sc, "metadata": {"strategy": "config_section_sub", "section": sec["section"]}})
            return chunks

        # Fallback to sliding window for unstructured config (JSON, YAML without section headers)
        return [{"text": c, "metadata": {"strategy": "config_window", "ext": ext}}
                for c in self._sliding_window_split(text, self.chunk_size, self.chunk_overlap)]

    # -------------------------------------------------------------------------
    # UTILITY: SLIDING WINDOW SPLIT
    # -------------------------------------------------------------------------
    def _sliding_window_split(self, text: str, chunk_size: int, overlap: int) -> List[str]:
        """Sliding window text split with word boundary snapping."""
        if len(text) <= chunk_size:
            return [text]

        chunks: List[str] = []
        start = 0
        text_len = len(text)

        while start < text_len:
            end = min(start + chunk_size, text_len)
            # Snap to word boundary if not at end of text
            if end < text_len:
                space_idx = text.rfind(" ", start, end)
                newline_idx = text.rfind("\n", start, end)
                best_break = max(space_idx, newline_idx)
                if best_break > start + (chunk_size // 2):
                    end = best_break

            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)

            if end >= text_len:
                break

            start = max(end - overlap, start + 1)

        return chunks
