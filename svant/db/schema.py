"""
SQLite database schema definitions and migrations for SVANT.
Includes project tracking, file metadata, text extractions, and FTS5 search index.
"""

from __future__ import annotations

import sqlite3
from svant.logger import get_logger

logger = get_logger("svant.db.schema")

SCHEMA_SQL = """
-- 1. Projects Table
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    root_path TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'ready',
    file_count INTEGER NOT NULL DEFAULT 0,
    total_size_bytes INTEGER NOT NULL DEFAULT 0,
    last_scanned_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 2. Files Table
CREATE TABLE IF NOT EXISTS files (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    path TEXT NOT NULL UNIQUE,
    relative_path TEXT NOT NULL,
    filename TEXT NOT NULL,
    extension TEXT NOT NULL,
    category TEXT NOT NULL,
    mime_type TEXT,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    created_time TEXT,
    modified_time TEXT NOT NULL,
    sha256 TEXT,
    scan_status TEXT NOT NULL DEFAULT 'scanned',
    indexed_status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 3. File Extractions Table
CREATE TABLE IF NOT EXISTS file_extractions (
    file_id TEXT PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    content_text TEXT,
    char_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'extracted',
    error_message TEXT,
    extracted_at TEXT NOT NULL
);

-- 4. FTS5 Keyword Search Virtual Table
CREATE VIRTUAL TABLE IF NOT EXISTS fts_files USING fts5(
    file_id UNINDEXED,
    project_id UNINDEXED,
    filename,
    relative_path,
    content,
    tokenize='porter unicode61'
);

-- 5. Semantic Chunks Table (Phase 2)
CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    vector_id INTEGER UNIQUE NOT NULL,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    file_id TEXT NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    char_count INTEGER NOT NULL DEFAULT 0,
    word_count INTEGER NOT NULL DEFAULT 0,
    content_type TEXT NOT NULL DEFAULT 'document',
    metadata_json TEXT,
    sha256 TEXT,
    created_at TEXT NOT NULL
);

-- 6. Project Vector Index Tracking (Phase 2)
CREATE TABLE IF NOT EXISTS project_indexes (
    project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'not_indexed',
    model_name TEXT,
    dimension INTEGER,
    total_chunks INTEGER NOT NULL DEFAULT 0,
    total_vectors INTEGER NOT NULL DEFAULT 0,
    last_indexed_at TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 7. Standard Indexes for High Performance
CREATE INDEX IF NOT EXISTS idx_files_project_id ON files(project_id);
CREATE INDEX IF NOT EXISTS idx_files_category ON files(category);
CREATE INDEX IF NOT EXISTS idx_files_extension ON files(extension);
CREATE INDEX IF NOT EXISTS idx_files_modified ON files(modified_time);
CREATE INDEX IF NOT EXISTS idx_extractions_project ON file_extractions(project_id);
CREATE INDEX IF NOT EXISTS idx_chunks_project_id ON chunks(project_id);
CREATE INDEX IF NOT EXISTS idx_chunks_file_id ON chunks(file_id);
CREATE INDEX IF NOT EXISTS idx_chunks_vector_id ON chunks(vector_id);
"""


def init_db(conn: sqlite3.Connection) -> None:
    """Initialize database tables, indexes, and virtual tables."""
    logger.debug("Initializing database schema...")
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    logger.debug("Database schema initialized successfully.")
