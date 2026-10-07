"""
Unit tests for Citation Generator (Phase 3).
Verifies accurate source file attribution, location, and snippet formatting.
"""

import pytest
from svant.core.rag.citations import CitationGenerator, Citation
from svant.core.rag.context import ContextItem


def test_generate_citations_with_line_numbers():
    items = [
        ContextItem(
            chunk_id="c1",
            file_id="f1",
            project_id="p1",
            relative_path="svant/core/search.py",
            filename="search.py",
            content="class SearchService:\n    def search(): pass",
            relevance_score=0.91234,
            chunk_index=0,
            line_start=10,
            line_end=25,
        ),
    ]

    citations = CitationGenerator.generate(items)
    assert len(citations) == 1
    c = citations[0]
    assert c.file_id == "f1"
    assert c.filename == "search.py"
    assert c.relative_path == "svant/core/search.py"
    assert "Lines 10" in c.location
    assert c.relevance_score == 0.9123
    assert "class SearchService:" in c.snippet_preview


def test_generate_citations_fallback_chunk_label():
    items = [
        ContextItem(
            chunk_id="c2",
            file_id="f2",
            project_id="p1",
            relative_path="docs/architecture.md",
            filename="architecture.md",
            content="# Architecture Overview\nSVANT uses SQLite and FAISS.",
            relevance_score=0.85,
            chunk_index=2,
        ),
    ]

    citations = CitationGenerator.generate(items)
    assert len(citations) == 1
    c = citations[0]
    assert "Chunk 3" in c.location


def test_generate_citations_deduplicates():
    item1 = ContextItem(
        chunk_id="c1",
        file_id="f1",
        project_id="p1",
        relative_path="file.py",
        filename="file.py",
        content="print('A')",
        relevance_score=0.9,
        chunk_index=0,
        line_start=1,
        line_end=2,
    )
    item2 = ContextItem(
        chunk_id="c1",
        file_id="f1",
        project_id="p1",
        relative_path="file.py",
        filename="file.py",
        content="print('A')",
        relevance_score=0.8,
        chunk_index=0,
        line_start=1,
        line_end=2,
    )

    citations = CitationGenerator.generate([item1, item2])
    assert len(citations) == 1
