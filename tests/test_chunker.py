"""
Tests for text chunking engine in SVANT Phase 2.
"""

from __future__ import annotations

import pytest
from svant.core.chunker import TextChunker, TextChunk


def test_chunk_empty_and_whitespace():
    chunker = TextChunker(chunk_size=200, chunk_overlap=30)
    assert chunker.chunk_document("p1", "f1", "test.txt", "test.txt", "") == []
    assert chunker.chunk_document("p1", "f1", "test.txt", "test.txt", "   \n\n  ") == []


def test_chunk_metadata_retention():
    chunker = TextChunker(chunk_size=150, chunk_overlap=20)
    text = "Line 1 of content.\n\nLine 2 of content.\n\nLine 3 of content with more details."
    chunks = chunker.chunk_document(
        project_id="proj-123",
        file_id="file-456",
        relative_path="docs/guide.txt",
        filename="guide.txt",
        text=text,
        category="document",
    )

    assert len(chunks) > 0
    for idx, c in enumerate(chunks):
        assert isinstance(c, TextChunk)
        assert c.project_id == "proj-123"
        assert c.file_id == "file-456"
        assert c.relative_path == "docs/guide.txt"
        assert c.filename == "guide.txt"
        assert c.chunk_index == idx
        assert c.content_type == "document"
        assert c.char_count == len(c.text)
        assert c.word_count == len(c.text.split())
        assert "relative_path" in c.metadata


def test_chunk_markdown_heading_boundaries():
    chunker = TextChunker(chunk_size=120, chunk_overlap=20)
    md = """# Introduction
SVANT is a local-first file intelligence platform.

## Architecture
It uses SQLite and FAISS for fast local queries without cloud exposure.

### Components
The scanner crawls local disks and extracts clean text safely.
"""
    chunks = chunker.chunk_document("p1", "f1", "README.md", "README.md", md, category="document")
    assert len(chunks) >= 3

    # Headers should be captured in metadata
    headers = [c.metadata.get("section") for c in chunks if "section" in c.metadata]
    assert any("Introduction" in h for h in headers)
    assert any("Architecture" in h for h in headers)
    assert any("Components" in h for h in headers)


def test_chunk_source_code_function_boundaries():
    chunker = TextChunker(chunk_size=150, chunk_overlap=20)
    code = '''
def add(a: int, b: int) -> int:
    """Add two numbers and return sum."""
    return a + b

def multiply(x: int, y: int) -> int:
    """Multiply two numbers and return product."""
    result = x * y
    return result

class MathService:
    def calculate(self, val: int) -> int:
        return val * 2
'''
    chunks = chunker.chunk_document("p1", "f1", "calc.py", "calc.py", code, category="source")
    assert len(chunks) >= 2

    # Check code metadata
    strategies = [c.metadata.get("strategy") for c in chunks]
    assert any("code_" in str(s) for s in strategies)


def test_chunk_csv_header_preservation():
    chunker = TextChunker(chunk_size=100, chunk_overlap=10)
    csv_text = """id,name,role,department
1,Alice,Engineer,Core Platform
2,Bob,Architect,Infrastructure
3,Charlie,Designer,User Experience
4,Diana,Scientist,Machine Learning
5,Evan,Analyst,Data Intelligence
"""
    chunks = chunker.chunk_document("p1", "f1", "users.csv", "users.csv", csv_text, category="data")
    assert len(chunks) >= 2

    # Every chunk should contain the header line
    for c in chunks:
        assert "id,name,role,department" in c.text


def test_chunk_config_sections():
    chunker = TextChunker(chunk_size=120, chunk_overlap=15)
    ini_text = """[database]
host = 127.0.0.1
port = 5432
name = svant_db

[storage]
data_dir = /var/svant/data
indexes = /var/svant/indexes

[logging]
level = INFO
format = json
"""
    chunks = chunker.chunk_document("p1", "f1", "app.ini", "app.ini", ini_text, category="config")
    assert len(chunks) >= 2
    sections = [c.metadata.get("section") for c in chunks]
    assert any(s in ("database", "storage", "logging") for s in sections)


def test_chunk_large_text_sliding_window():
    chunker = TextChunker(chunk_size=200, chunk_overlap=40)
    # Generate 1500 chars of prose
    long_text = " ".join([f"This is sentence number {i} discussing important local system concepts." for i in range(50)])
    chunks = chunker.chunk_document("p1", "f1", "long.txt", "long.txt", long_text, category="document")

    assert len(chunks) > 4
    for c in chunks:
        # Check no chunk is excessively oversized
        assert len(c.text) <= 350
        assert len(c.text) >= 30
