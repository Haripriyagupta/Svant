"""
Repository layer for parameterized SQLite queries in SVANT.
Implements data access for projects, files, text extractions, and FTS5 search.
"""

from __future__ import annotations

import datetime
import json
import sqlite3
import threading
import uuid
from typing import Any, Dict, List, Optional, Set

from svant.db.connection import DatabaseManager
from svant.db.schema import init_db
from svant.logger import get_logger

logger = get_logger("svant.db.repository")

_vector_id_lock = threading.Lock()


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class Repository:
    """Data access repository for SVANT database."""

    def __init__(self, db_manager: DatabaseManager) -> None:
        self.db = db_manager
        with self.db.session() as conn:
            init_db(conn)

    # =========================================================================
    # PROJECTS
    # =========================================================================

    def create_project(self, name: str, root_path: str) -> Dict[str, Any]:
        """Create a new tracked project."""
        project_id = str(uuid.uuid4())
        now = _now_iso()
        with self.db.session() as conn:
            conn.execute(
                """
                INSERT INTO projects (id, name, root_path, status, file_count, total_size_bytes, created_at, updated_at)
                VALUES (?, ?, ?, 'ready', 0, 0, ?, ?)
                """,
                (project_id, name, root_path, now, now),
            )
        return self.get_project(project_id) or {}

    def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a project by ID."""
        with self.db.session() as conn:
            cursor = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_project_by_path(self, root_path: str) -> Optional[Dict[str, Any]]:
        """Retrieve a project by normalized root path."""
        with self.db.session() as conn:
            cursor = conn.execute("SELECT * FROM projects WHERE root_path = ?", (root_path,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def list_projects(self) -> List[Dict[str, Any]]:
        """List all tracked projects ordered by updated date descending."""
        with self.db.session() as conn:
            cursor = conn.execute("SELECT * FROM projects ORDER BY updated_at DESC")
            return [dict(row) for row in cursor.fetchall()]

    def update_project(
        self,
        project_id: str,
        status: Optional[str] = None,
        file_count: Optional[int] = None,
        total_size_bytes: Optional[int] = None,
        last_scanned_at: Optional[str] = None,
    ) -> None:
        """Update status and summary metrics for a project."""
        fields: List[str] = []
        params: List[Any] = []

        if status is not None:
            fields.append("status = ?")
            params.append(status)
        if file_count is not None:
            fields.append("file_count = ?")
            params.append(file_count)
        if total_size_bytes is not None:
            fields.append("total_size_bytes = ?")
            params.append(total_size_bytes)
        if last_scanned_at is not None:
            fields.append("last_scanned_at = ?")
            params.append(last_scanned_at)

        fields.append("updated_at = ?")
        params.append(_now_iso())
        params.append(project_id)

        query = f"UPDATE projects SET {', '.join(fields)} WHERE id = ?"
        with self.db.session() as conn:
            conn.execute(query, params)

    def delete_project(self, project_id: str) -> bool:
        """
        Delete a project and all associated DB records (files, extractions, FTS index).
        Does NOT touch or delete real files on disk.
        """
        with self.db.session() as conn:
            # Clean up FTS entries for this project
            conn.execute("DELETE FROM fts_files WHERE project_id = ?", (project_id,))
            # Delete project row (foreign key CASCADE takes care of files and file_extractions)
            cursor = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            return cursor.rowcount > 0

    # =========================================================================
    # FILES
    # =========================================================================

    def upsert_file(
        self,
        project_id: str,
        path: str,
        relative_path: str,
        filename: str,
        extension: str,
        category: str,
        size_bytes: int,
        modified_time: str,
        created_time: Optional[str] = None,
        mime_type: Optional[str] = None,
        sha256: Optional[str] = None,
        scan_status: str = "scanned",
        indexed_status: str = "pending",
    ) -> Dict[str, Any]:
        """Insert or update file metadata."""
        now = _now_iso()
        existing = self.get_file_by_path(path)
        if existing:
            file_id = existing["id"]
            with self.db.session() as conn:
                conn.execute(
                    """
                    UPDATE files SET
                        project_id = ?,
                        relative_path = ?,
                        filename = ?,
                        extension = ?,
                        category = ?,
                        mime_type = ?,
                        size_bytes = ?,
                        created_time = ?,
                        modified_time = ?,
                        sha256 = ?,
                        scan_status = ?,
                        indexed_status = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        project_id,
                        relative_path,
                        filename,
                        extension,
                        category,
                        mime_type,
                        size_bytes,
                        created_time,
                        modified_time,
                        sha256,
                        scan_status,
                        indexed_status,
                        now,
                        file_id,
                    ),
                )
        else:
            file_id = str(uuid.uuid4())
            with self.db.session() as conn:
                conn.execute(
                    """
                    INSERT INTO files (
                        id, project_id, path, relative_path, filename, extension,
                        category, mime_type, size_bytes, created_time, modified_time,
                        sha256, scan_status, indexed_status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        file_id,
                        project_id,
                        path,
                        relative_path,
                        filename,
                        extension,
                        category,
                        mime_type,
                        size_bytes,
                        created_time,
                        modified_time,
                        sha256,
                        scan_status,
                        indexed_status,
                        now,
                        now,
                    ),
                )
        return self.get_file(file_id) or {}

    def get_file(self, file_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a file by ID."""
        with self.db.session() as conn:
            cursor = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_file_by_path(self, path: str) -> Optional[Dict[str, Any]]:
        """Retrieve a file by absolute path."""
        with self.db.session() as conn:
            cursor = conn.execute("SELECT * FROM files WHERE path = ?", (path,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def list_files(
        self,
        project_id: Optional[str] = None,
        category: Optional[str] = None,
        extension: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Query scanned files with filters and pagination."""
        clauses: List[str] = []
        params: List[Any] = []

        if project_id:
            clauses.append("f.project_id = ?")
            params.append(project_id)
        if category:
            clauses.append("f.category = ?")
            params.append(category)
        if extension:
            clauses.append("f.extension = ?")
            params.append(extension.lower())
        if search:
            clauses.append("(f.filename LIKE ? OR f.relative_path LIKE ?)")
            term = f"%{search}%"
            params.extend([term, term])

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"""
            SELECT f.*, p.name AS project_name
            FROM files f
            JOIN projects p ON f.project_id = p.id
            {where_sql}
            ORDER BY f.modified_time DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        with self.db.session() as conn:
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def count_files(
        self,
        project_id: Optional[str] = None,
        category: Optional[str] = None,
        extension: Optional[str] = None,
        search: Optional[str] = None,
    ) -> int:
        """Count total files matching the criteria."""
        clauses: List[str] = []
        params: List[Any] = []

        if project_id:
            clauses.append("project_id = ?")
            params.append(project_id)
        if category:
            clauses.append("category = ?")
            params.append(category)
        if extension:
            clauses.append("extension = ?")
            params.append(extension.lower())
        if search:
            clauses.append("(filename LIKE ? OR relative_path LIKE ?)")
            term = f"%{search}%"
            params.extend([term, term])

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"SELECT COUNT(*) FROM files {where_sql}"

        with self.db.session() as conn:
            cursor = conn.execute(query, params)
            return cursor.fetchone()[0]

    def delete_stale_files(self, project_id: str, active_paths: Set[str]) -> int:
        """
        Remove DB records for files no longer present on disk during a rescan.
        Does not touch files on disk.
        """
        with self.db.session() as conn:
            cursor = conn.execute("SELECT id, path FROM files WHERE project_id = ?", (project_id,))
            current_files = cursor.fetchall()
            stale_ids = [row["id"] for row in current_files if row["path"] not in active_paths]

            if not stale_ids:
                return 0

            # Remove from FTS index
            placeholders = ",".join("?" for _ in stale_ids)
            conn.execute(f"DELETE FROM fts_files WHERE file_id IN ({placeholders})", stale_ids)
            # Remove from files table
            del_cursor = conn.execute(f"DELETE FROM files WHERE id IN ({placeholders})", stale_ids)
            return del_cursor.rowcount

    def update_file_index_status(self, file_id: str, status: str) -> None:
        """Update file indexing state ('indexed', 'skipped', 'failed')."""
        with self.db.session() as conn:
            conn.execute(
                "UPDATE files SET indexed_status = ?, updated_at = ? WHERE id = ?",
                (status, _now_iso(), file_id),
            )

    # =========================================================================
    # EXTRACTIONS
    # =========================================================================

    def upsert_extraction(
        self,
        file_id: str,
        project_id: str,
        content_text: Optional[str],
        char_count: int,
        status: str,
        error_message: Optional[str] = None,
    ) -> None:
        """Store extracted text and status for a document/file."""
        now = _now_iso()
        with self.db.session() as conn:
            conn.execute(
                """
                INSERT INTO file_extractions (file_id, project_id, content_text, char_count, status, error_message, extracted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(file_id) DO UPDATE SET
                    content_text = excluded.content_text,
                    char_count = excluded.char_count,
                    status = excluded.status,
                    error_message = excluded.error_message,
                    extracted_at = excluded.extracted_at
                """,
                (file_id, project_id, content_text, char_count, status, error_message, now),
            )

    def get_extraction(self, file_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve extraction details and text preview for a file."""
        with self.db.session() as conn:
            cursor = conn.execute("SELECT * FROM file_extractions WHERE file_id = ?", (file_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    # =========================================================================
    # FTS5 SEARCH
    # =========================================================================

    def index_file_fts(
        self,
        file_id: str,
        project_id: str,
        filename: str,
        relative_path: str,
        content: str,
    ) -> None:
        """Index a file's content and path in SQLite FTS5."""
        with self.db.session() as conn:
            # Delete old entry if exists to avoid duplicates
            conn.execute("DELETE FROM fts_files WHERE file_id = ?", (file_id,))
            conn.execute(
                """
                INSERT INTO fts_files (file_id, project_id, filename, relative_path, content)
                VALUES (?, ?, ?, ?, ?)
                """,
                (file_id, project_id, filename, relative_path, content),
            )

    def search_fts(
        self,
        query: str,
        project_id: Optional[str] = None,
        limit: int = 25,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Execute full-text keyword search against SQLite FTS5.
        Returns matching records with snippets and relevance rank.
        """
        clean_query = query.strip()
        if not clean_query:
            return []

        # Sanitize query terms for safe FTS5 MATCH syntax
        tokens = [t.replace('"', '""') for t in clean_query.split() if t]
        if not tokens:
            return []
        fts_match_query = " ".join(f'"{token}"*' for token in tokens)

        params: List[Any] = [fts_match_query]
        project_filter = ""
        if project_id:
            project_filter = "AND fts.project_id = ?"
            params.append(project_id)

        params.extend([limit, offset])

        sql = f"""
            SELECT
                fts.file_id,
                fts.project_id,
                fts.filename,
                fts.relative_path,
                snippet(fts_files, 4, '<mark>', '</mark>', '...', 24) AS snippet,
                bm25(fts_files) AS rank,
                f.category,
                f.size_bytes,
                f.modified_time,
                p.name AS project_name
            FROM fts_files fts
            JOIN files f ON fts.file_id = f.id
            JOIN projects p ON fts.project_id = p.id
            WHERE fts_files MATCH ? {project_filter}
            ORDER BY rank
            LIMIT ? OFFSET ?
        """

        with self.db.session() as conn:
            try:
                cursor = conn.execute(sql, params)
                return [dict(row) for row in cursor.fetchall()]
            except sqlite3.OperationalError as e:
                logger.warning(f"FTS5 search syntax error on query '{clean_query}': {e}")
                # Fallback to plain quoted phrase if wildcard expansion fails
                fallback_sql = sql.replace("WHERE fts_files MATCH ?", "WHERE fts_files MATCH ?")
                fallback_params = [f'"{clean_query}"']
                if project_id:
                    fallback_params.append(project_id)
                fallback_params.extend([limit, offset])
                cursor = conn.execute(fallback_sql, fallback_params)
                return [dict(row) for row in cursor.fetchall()]

    # =========================================================================
    # DASHBOARD & STATS
    # =========================================================================

    def get_dashboard_stats(self) -> Dict[str, Any]:
        """Aggregate system metrics for the dashboard view."""
        with self.db.session() as conn:
            proj_count = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
            file_count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
            total_size = conn.execute("SELECT COALESCE(SUM(size_bytes), 0) FROM files").fetchone()[0]
            indexed_count = conn.execute("SELECT COUNT(*) FROM file_extractions WHERE status = 'extracted'").fetchone()[0]

            latest_scan_row = conn.execute(
                "SELECT last_scanned_at FROM projects WHERE last_scanned_at IS NOT NULL ORDER BY last_scanned_at DESC LIMIT 1"
            ).fetchone()
            last_scan = latest_scan_row[0] if latest_scan_row else None

            # Category distribution
            cat_rows = conn.execute(
                "SELECT category, COUNT(*) as cnt, COALESCE(SUM(size_bytes), 0) as sz FROM files GROUP BY category"
            ).fetchall()
            categories = {row["category"]: {"count": row["cnt"], "size": row["sz"]} for row in cat_rows}

            total_chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]

            return {
                "total_projects": proj_count,
                "total_files": file_count,
                "total_size_bytes": total_size,
                "total_indexed_files": indexed_count,
                "total_chunks": total_chunks,
                "last_scanned_at": last_scan,
                "categories": categories,
                "database_status": "connected",
            }

    # =========================================================================
    # PHASE 2: CHUNKS & VECTOR MAPPINGS
    # =========================================================================

    def insert_chunks(self, chunks_data: List[Dict[str, Any]]) -> List[int]:
        """
        Store a batch of text chunks, allocating unique 64-bit vector IDs.
        Returns the list of allocated vector IDs.
        """
        if not chunks_data:
            return []

        now = _now_iso()
        with _vector_id_lock:
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    with self.db.session() as conn:
                        cur = conn.execute("SELECT COALESCE(MAX(vector_id), 0) FROM chunks")
                        max_id = cur.fetchone()[0]
                        start_id = max_id + 1

                        assigned_vector_ids: List[int] = []
                        rows_to_insert = []

                        for idx, c in enumerate(chunks_data):
                            vid = start_id + idx
                            assigned_vector_ids.append(vid)
                            meta_json = json.dumps(c.get("metadata", {}))
                            rows_to_insert.append((
                                c.get("id") or str(uuid.uuid4()),
                                vid,
                                c["project_id"],
                                c["file_id"],
                                c.get("chunk_index", 0),
                                c["text"],
                                c.get("char_count", len(c["text"])),
                                c.get("word_count", len(c["text"].split())),
                                c.get("content_type", "document"),
                                meta_json,
                                c.get("sha256"),
                                now,
                            ))

                        conn.executemany(
                            """
                            INSERT INTO chunks (
                                id, vector_id, project_id, file_id, chunk_index,
                                text, char_count, word_count, content_type,
                                metadata_json, sha256, created_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            rows_to_insert,
                        )

                        return assigned_vector_ids
                except sqlite3.IntegrityError as e:
                    if "chunks.vector_id" in str(e) and attempt < max_retries - 1:
                        logger.warning(f"Vector ID collision on attempt {attempt + 1}, retrying: {e}")
                        continue
                    raise

    def get_chunks_by_file(self, file_id: str) -> List[Dict[str, Any]]:
        """Retrieve all chunks for a specific file ordered by chunk index."""
        with self.db.session() as conn:
            cursor = conn.execute(
                "SELECT * FROM chunks WHERE file_id = ? ORDER BY chunk_index ASC",
                (file_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_chunks_by_project(self, project_id: str) -> List[Dict[str, Any]]:
        """Retrieve all chunks for a project."""
        with self.db.session() as conn:
            cursor = conn.execute(
                "SELECT * FROM chunks WHERE project_id = ? ORDER BY file_id, chunk_index ASC",
                (project_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def count_chunks_by_project(self, project_id: str) -> int:
        """Count total chunks for a project."""
        with self.db.session() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM chunks WHERE project_id = ?", (project_id,))
            return cursor.fetchone()[0]

    def delete_chunks_by_file(self, file_id: str) -> List[int]:
        """
        Delete all chunks for a file, returning the deleted vector IDs so FAISS can drop them.
        """
        with self.db.session() as conn:
            cursor = conn.execute("SELECT vector_id FROM chunks WHERE file_id = ?", (file_id,))
            vector_ids = [row[0] for row in cursor.fetchall()]
            if vector_ids:
                conn.execute("DELETE FROM chunks WHERE file_id = ?", (file_id,))
            return vector_ids

    def delete_chunks_by_project(self, project_id: str) -> List[int]:
        """
        Delete all chunks for a project, returning the deleted vector IDs.
        """
        with self.db.session() as conn:
            cursor = conn.execute("SELECT vector_id FROM chunks WHERE project_id = ?", (project_id,))
            vector_ids = [row[0] for row in cursor.fetchall()]
            if vector_ids:
                conn.execute("DELETE FROM chunks WHERE project_id = ?", (project_id,))
            return vector_ids

    def get_chunks_by_vector_ids(self, vector_ids: List[int]) -> List[Dict[str, Any]]:
        """
        Lookup chunk metadata, file path, and project name by vector IDs.
        Preserves ordering requested or returns indexed map.
        """
        if not vector_ids:
            return []

        placeholders = ",".join("?" for _ in vector_ids)
        sql = f"""
            SELECT
                c.id AS chunk_id,
                c.vector_id,
                c.project_id,
                c.file_id,
                c.chunk_index,
                c.text,
                c.char_count,
                c.word_count,
                c.content_type,
                c.metadata_json,
                f.path,
                f.relative_path,
                f.filename,
                f.category,
                f.size_bytes,
                f.modified_time,
                p.name AS project_name
            FROM chunks c
            JOIN files f ON c.file_id = f.id
            JOIN projects p ON c.project_id = p.id
            WHERE c.vector_id IN ({placeholders})
        """

        with self.db.session() as conn:
            cursor = conn.execute(sql, vector_ids)
            rows = cursor.fetchall()

            # Map by vector_id to preserve the caller's score-ordered sequence
            by_id = {row["vector_id"]: dict(row) for row in rows}
            ordered_results = []
            for vid in vector_ids:
                if vid in by_id:
                    item = by_id[vid]
                    if item.get("metadata_json"):
                        try:
                            item["metadata"] = json.loads(item["metadata_json"])
                        except Exception:
                            item["metadata"] = {}
                    else:
                        item["metadata"] = {}
                    ordered_results.append(item)
            return ordered_results

    # =========================================================================
    # PHASE 2: PROJECT INDEX STATUS
    # =========================================================================

    def get_project_index_status(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve vector index state for a project."""
        with self.db.session() as conn:
            cursor = conn.execute("SELECT * FROM project_indexes WHERE project_id = ?", (project_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def upsert_project_index_status(
        self,
        project_id: str,
        status: str,
        model_name: Optional[str] = None,
        dimension: Optional[int] = None,
        total_chunks: Optional[int] = None,
        total_vectors: Optional[int] = None,
        last_indexed_at: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update or create the vector index state record for a project."""
        now = _now_iso()
        existing = self.get_project_index_status(project_id)

        with self.db.session() as conn:
            if existing:
                fields: List[str] = ["status = ?", "updated_at = ?"]
                params: List[Any] = [status, now]

                if model_name is not None:
                    fields.append("model_name = ?")
                    params.append(model_name)
                if dimension is not None:
                    fields.append("dimension = ?")
                    params.append(dimension)
                if total_chunks is not None:
                    fields.append("total_chunks = ?")
                    params.append(total_chunks)
                if total_vectors is not None:
                    fields.append("total_vectors = ?")
                    params.append(total_vectors)
                if last_indexed_at is not None:
                    fields.append("last_indexed_at = ?")
                    params.append(last_indexed_at)
                if error_message is not None:
                    fields.append("error_message = ?")
                    params.append(error_message)
                elif status == "indexed":
                    fields.append("error_message = NULL")

                params.append(project_id)
                conn.execute(f"UPDATE project_indexes SET {', '.join(fields)} WHERE project_id = ?", params)
            else:
                conn.execute(
                    """
                    INSERT INTO project_indexes (
                        project_id, status, model_name, dimension,
                        total_chunks, total_vectors, last_indexed_at,
                        error_message, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        project_id,
                        status,
                        model_name or "",
                        dimension or 0,
                        total_chunks or 0,
                        total_vectors or 0,
                        last_indexed_at,
                        error_message,
                        now,
                        now,
                    ),
                )

        return self.get_project_index_status(project_id) or {}

