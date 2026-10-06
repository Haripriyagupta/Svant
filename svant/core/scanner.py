"""
File scanning engine for SVANT.
Safely crawls project trees, collects file metadata, handles exclusions,
and coordinates text extraction with SQLite FTS5 indexing.
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, NamedTuple, Optional, Set

from svant.config import settings
from svant.core.classifier import FileClassifier
from svant.core.extractor import DocumentExtractor
from svant.db.repository import Repository
from svant.logger import get_logger

logger = get_logger("svant.core.scanner")


class ScannedFileInfo(NamedTuple):
    path: str
    relative_path: str
    filename: str
    extension: str
    category: str
    size_bytes: int
    modified_time: str
    created_time: Optional[str]
    sha256: Optional[str]
    scan_status: str


class ScanSummary(NamedTuple):
    project_id: str
    total_scanned: int
    total_size_bytes: int
    indexed_count: int
    failed_count: int
    duration_seconds: float


def _compute_sha256(path: Path, max_bytes: int = 20 * 1024 * 1024) -> Optional[str]:
    """Compute SHA-256 for files up to max_bytes to conserve CPU and I/O."""
    try:
        if path.stat().st_size > max_bytes:
            return None
        hasher = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception:
        return None


class FileScanner:
    """Safe, recursive file scanner for local projects."""

    def __init__(
        self,
        repo: Repository,
        extractor: Optional[DocumentExtractor] = None,
        excluded_dirs: Optional[List[str]] = None,
    ) -> None:
        self.repo = repo
        self.extractor = extractor or DocumentExtractor()
        self.excluded_dirs = set(excluded_dirs or settings.excluded_dirs)

    def is_excluded_dir(self, dir_name: str) -> bool:
        """Check whether a directory name matches the exclusion rules."""
        return dir_name.lower() in {d.lower() for d in self.excluded_dirs}

    def scan_project(
        self,
        project_id: str,
        extract_text: bool = True,
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> ScanSummary:
        """
        Scan a tracked project folder, store metadata, extract text, and index.
        Never executes any project code or modifies original files.
        """
        start_time = datetime.now(timezone.utc)
        project = self.repo.get_project(project_id)
        if not project:
            raise ValueError(f"Project with ID '{project_id}' not found.")

        root_path = Path(project["root_path"]).resolve()
        if not root_path.is_dir():
            self.repo.update_project(project_id, status="error")
            raise FileNotFoundError(f"Project root directory '{root_path}' does not exist or is not a directory.")

        logger.info(f"Starting scan for project '{project['name']}' at '{root_path}'")
        self.repo.update_project(project_id, status="scanning")

        active_file_paths: Set[str] = set()
        total_scanned = 0
        total_size = 0
        indexed_count = 0
        failed_count = 0

        try:
            for root, dirs, files in os.walk(str(root_path), topdown=True, followlinks=False):
                # Prune excluded directories in-place
                dirs[:] = [d for d in dirs if not self.is_excluded_dir(d)]

                for file_name in files:
                    full_file_path = Path(root) / file_name
                    active_file_paths.add(str(full_file_path))
                    total_scanned += 1

                    try:
                        stat = full_file_path.stat()
                        size_bytes = stat.st_size
                        total_size += size_bytes
                        mtime_iso = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()
                        try:
                            ctime_iso = datetime.fromtimestamp(stat.st_ctime, timezone.utc).isoformat()
                        except Exception:
                            ctime_iso = None

                        rel_path = str(full_file_path.relative_to(root_path)).replace("\\", "/")
                        classification = FileClassifier.classify(full_file_path)
                        sha256 = _compute_sha256(full_file_path)

                        # Upsert file metadata in SQLite
                        file_record = self.repo.upsert_file(
                            project_id=project_id,
                            path=str(full_file_path),
                            relative_path=rel_path,
                            filename=file_name,
                            extension=classification.extension,
                            category=classification.category.value,
                            mime_type=classification.mime_type,
                            size_bytes=size_bytes,
                            modified_time=mtime_iso,
                            created_time=ctime_iso,
                            sha256=sha256,
                            scan_status="scanned",
                            indexed_status="pending",
                        )

                        # Extract text and index in FTS5 if applicable
                        if extract_text and classification.is_text_extractable:
                            ext_res = self.extractor.extract(full_file_path)
                            self.repo.upsert_extraction(
                                file_id=file_record["id"],
                                project_id=project_id,
                                content_text=ext_res.text,
                                char_count=ext_res.char_count,
                                status=ext_res.status,
                                error_message=ext_res.error,
                            )

                            if ext_res.status == "extracted" and ext_res.text:
                                self.repo.index_file_fts(
                                    file_id=file_record["id"],
                                    project_id=project_id,
                                    filename=file_name,
                                    relative_path=rel_path,
                                    content=ext_res.text,
                                )
                                self.repo.update_file_index_status(file_record["id"], "indexed")
                                indexed_count += 1
                            elif ext_res.status == "failed":
                                self.repo.update_file_index_status(file_record["id"], "failed")
                                failed_count += 1
                            else:
                                self.repo.update_file_index_status(file_record["id"], "skipped")
                        else:
                            self.repo.update_file_index_status(file_record["id"], "skipped")

                    except (PermissionError, OSError) as os_err:
                        logger.warning(f"OS error reading file '{full_file_path}': {os_err}")
                        failed_count += 1
                        try:
                            rel_path = str(full_file_path.relative_to(root_path)).replace("\\", "/")
                        except Exception:
                            rel_path = file_name
                        self.repo.upsert_file(
                            project_id=project_id,
                            path=str(full_file_path),
                            relative_path=rel_path,
                            filename=file_name,
                            extension=Path(file_name).suffix.lower(),
                            category="other",
                            size_bytes=0,
                            modified_time=datetime.now(timezone.utc).isoformat(),
                            scan_status="unreadable",
                            indexed_status="failed",
                        )
                    except Exception as unexpected_err:
                        logger.warning(f"Unexpected error processing '{full_file_path}': {unexpected_err}")
                        failed_count += 1

                    if progress_callback and total_scanned % 50 == 0:
                        progress_callback(total_scanned, file_name)

            # Purge records of files that have been deleted from disk
            self.repo.delete_stale_files(project_id, active_file_paths)

            end_time = datetime.now(timezone.utc)
            duration = (end_time - start_time).total_seconds()
            now_iso = end_time.isoformat()

            self.repo.update_project(
                project_id=project_id,
                status="ready",
                file_count=total_scanned,
                total_size_bytes=total_size,
                last_scanned_at=now_iso,
            )

            logger.info(
                f"Completed scan for '{project['name']}': {total_scanned} files ({total_size} bytes), "
                f"{indexed_count} indexed in {duration:.2f}s"
            )

            return ScanSummary(
                project_id=project_id,
                total_scanned=total_scanned,
                total_size_bytes=total_size,
                indexed_count=indexed_count,
                failed_count=failed_count,
                duration_seconds=duration,
            )

        except Exception as scan_err:
            logger.error(f"Fatal scan error on project {project_id}: {scan_err}")
            self.repo.update_project(project_id, status="error")
            raise
