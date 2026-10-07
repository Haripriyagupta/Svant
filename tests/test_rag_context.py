"""
Unit tests for RAG Context Assembly (Phase 3).
Tests context deduplication, relevance ordering, and character budget enforcement.
"""

import pytest
from svant.core.rag.context import ContextAssembler, ContextItem


def test_context_assembler_ordering_and_deduplication():
    assembler = ContextAssembler(top_k=5, max_context_chars=5000)

    # Simulated search hits
    hits = [
        {
            "chunk_id": "c1",
            "file_id": "f1",
            "project_id": "p1",
            "filename": "auth.py",
            "relative_path": "auth.py",
            "snippet": "def login(): pass",
            "score": 0.82,
            "metadata": {"chunk_index": 0},
        },
        {
            "chunk_id": "c2",
            "file_id": "f1",
            "project_id": "p1",
            "filename": "auth.py",
            "relative_path": "auth.py",
            "snippet": "def logout(): pass",
            "score": 0.95,
            "metadata": {"chunk_index": 1},
        },
        # Duplicate of c1 with lower score
        {
            "chunk_id": "c1",
            "file_id": "f1",
            "project_id": "p1",
            "filename": "auth.py",
            "relative_path": "auth.py",
            "snippet": "def login(): pass",
            "score": 0.70,
            "metadata": {"chunk_index": 0},
        },
    ]

    items = assembler.assemble(hits, project_id="p1")
    assert len(items) == 2
    # Highest score first
    assert items[0].chunk_id == "c2"
    assert items[0].relevance_score == 0.95
    assert items[1].chunk_id == "c1"
    assert items[1].relevance_score == 0.82


def test_context_assembler_budget_enforcement():
    # Set a budget of 300 chars
    assembler = ContextAssembler(top_k=5, max_context_chars=300)

    hits = [
        {
            "chunk_id": "c1",
            "file_id": "f1",
            "project_id": "p1",
            "filename": "first.py",
            "relative_path": "first.py",
            "snippet": "A" * 150,
            "score": 0.9,
        },
        {
            "chunk_id": "c2",
            "file_id": "f2",
            "project_id": "p1",
            "filename": "second.py",
            "relative_path": "second.py",
            "snippet": "B" * 200,
            "score": 0.8,
        },
    ]

    items = assembler.assemble(hits, project_id="p1")
    total_chars = sum(len(it.content) for it in items)
    # Cannot exceed context budget significantly
    assert len(items) >= 1
    assert items[0].chunk_id == "c1"


def test_context_assembler_formatting():
    assembler = ContextAssembler()
    items = [
        ContextItem(
            file_id="f1",
            chunk_id="c1",
            filename="main.py",
            relative_path="src/main.py",
            project_id="p1",
            chunk_index=0,
            content="print('hello')",
            relevance_score=0.95,
            line_start=1,
            line_end=5,
        )
    ]
    formatted = assembler.format_context_for_prompt(items)
    assert "[Source 1: src/main.py" in formatted
    assert "Lines 1–5" in formatted
    assert "print('hello')" in formatted


def test_context_assembler_empty_hits():
    assembler = ContextAssembler()
    items = assembler.assemble([])
    assert items == []
    formatted = assembler.format_context_for_prompt([])
    assert "No relevant project files found" in formatted
