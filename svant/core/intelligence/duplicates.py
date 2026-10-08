"""
Duplicate and Near-Duplicate Detection Engine for SVANT.
Detects both exact duplicate files (via SHA-256 hash clustering)
and near-duplicate text files (via lightweight token and character similarity).
"""

from __future__ import annotations

import difflib
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from svant.db.repository import Repository
from svant.logger import get_logger

logger = get_logger("svant.core.intelligence.duplicates")

# Directories to exclude from duplicate detection
EXCLUDED_DIR_PATTERNS = {
    ".git", ".svn", ".hg", "node_modules", ".venv", "venv", "env",
    "dist", "build", "__pycache__", ".pytest_cache", ".ruff_cache",
    ".mypy_cache", ".idea", ".vscode", "coverage", ".next", ".nuxt",
}

# Extension groups to ensure similarity comparison happens within compatible file types
EXTENSION_GROUPS: Dict[str, str] = {
    ".py": "python", ".pyw": "python",
    ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "typescript",
    ".json": "json",
    ".yaml": "yaml", ".yml": "yaml",
    ".html": "html", ".htm": "html",
    ".css": "css", ".scss": "css", ".sass": "css", ".less": "css",
    ".md": "markdown", ".markdown": "markdown",
    ".txt": "text", ".text": "text", ".rst": "text",
    ".sh": "shell", ".bash": "shell", ".zsh": "shell",
    ".sql": "sql",
    ".xml": "xml", ".svg": "xml",
    ".c": "c_cpp", ".cpp": "c_cpp", ".cc": "c_cpp", ".h": "c_cpp", ".hpp": "c_cpp",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".php": "php",
    ".rb": "ruby",
}

# Suffixes that typically indicate minified or lock files to skip
SKIPPED_FILENAME_PATTERNS = (
    ".min.js", ".min.css", ".bundle.js", ".bundle.css",
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
    "composer.lock", "cargo.lock", ".map",
)


class DuplicateDetector:
    """
    Lightweight, CPU-friendly duplicate and near-duplicate detector.
    Identifies:
    1. Exact duplicates: Files sharing identical content (SHA-256 hash match, 100% similarity).
    2. Near-duplicates: Text-capable files sharing >= 85% content with minor modifications.
    """

    def __init__(
        self,
        repo: Repository,
        min_similarity: float = 0.85,
        max_comparisons: int = 1500,
        max_file_size: int = 512 * 1024,  # 512 KB
        min_file_size: int = 20,           # 20 bytes
    ) -> None:
        self.repo = repo
        self.min_similarity = min_similarity
        self.max_comparisons = max_comparisons
        self.max_file_size = max_file_size
        self.min_file_size = min_file_size

    def detect_duplicates(self, project_id: str) -> List[Dict[str, Any]]:
        """
        Scan project files and return combined exact and near-duplicate clusters.
        """
        # Step 1: Detect exact duplicates via SHA-256 hash
        exact_clusters, exact_file_ids = self._find_exact_duplicates(project_id)

        # Step 2: Detect near-duplicates via text similarity
        similar_clusters = self._find_near_duplicates(project_id, excluded_file_ids=exact_file_ids)

        # Combine results: exact duplicates first (sorted by wasted bytes desc),
        # followed by near-duplicates (sorted by similarity desc, then wasted bytes desc)
        exact_clusters.sort(key=lambda c: c.get("wasted_bytes", 0), reverse=True)
        similar_clusters.sort(key=lambda c: (c.get("similarity_pct", 0), c.get("wasted_bytes", 0)), reverse=True)

        return exact_clusters + similar_clusters

    def _find_exact_duplicates(self, project_id: str) -> Tuple[List[Dict[str, Any]], Set[str]]:
        """
        Find exact duplicate clusters using SHA-256 hashes.
        Designates the oldest file as 'original' and newer files as 'copy'.
        """
        sql = """
            SELECT sha256, COUNT(*) as count, SUM(size_bytes) as total_size, MIN(size_bytes) as file_size
            FROM files
            WHERE project_id = ? AND sha256 IS NOT NULL AND sha256 != ''
            GROUP BY sha256
            HAVING count > 1
            ORDER BY total_size DESC
        """
        clusters: List[Dict[str, Any]] = []
        claimed_file_ids: Set[str] = set()

        with self.repo.db.session() as conn:
            cursor = conn.execute(sql, (project_id,))
            cluster_rows = cursor.fetchall()

            for row in cluster_rows:
                h = row["sha256"]
                files_cur = conn.execute(
                    """
                    SELECT id, filename, relative_path, size_bytes, category, extension, modified_time, path
                    FROM files
                    WHERE project_id = ? AND sha256 = ?
                    ORDER BY modified_time ASC, id ASC
                    """,
                    (project_id, h),
                )
                raw_files = [dict(f) for f in files_cur.fetchall()]
                if len(raw_files) < 2:
                    continue

                cluster_files: List[Dict[str, Any]] = []
                for idx, f in enumerate(raw_files):
                    claimed_file_ids.add(f["id"])
                    is_primary = (idx == 0)
                    cluster_files.append({
                        "id": f["id"],
                        "filename": f["filename"],
                        "relative_path": f["relative_path"],
                        "size_bytes": f["size_bytes"],
                        "category": f["category"],
                        "extension": f.get("extension", ""),
                        "modified_time": f["modified_time"],
                        "role": "original" if is_primary else "copy",
                        "is_primary": is_primary,
                        "sha256": h,
                    })

                file_size = row["file_size"]
                count = row["count"]
                wasted_bytes = (count - 1) * file_size

                clusters.append({
                    "sha256": h,
                    "count": count,
                    "file_count": count,
                    "size_bytes": file_size,
                    "file_size": file_size,
                    "wasted_bytes": wasted_bytes,
                    "duplicate_type": "exact",
                    "cluster_type": "exact",
                    "similarity": 1.0,
                    "similarity_pct": 100,
                    "difference_summary": "Identical content (100% hash match)",
                    "reason": f"Identical content across {count} files (100% match via SHA-256)",
                    "primary_file": cluster_files[0],
                    "files": cluster_files,
                })

        return clusters, claimed_file_ids

    def _find_near_duplicates(
        self,
        project_id: str,
        excluded_file_ids: Set[str],
    ) -> List[Dict[str, Any]]:
        """
        Find near-duplicate text files with >= 85% content similarity.
        Applies mathematical length filters and extension bucketing to avoid O(N^2) bottlenecks.
        """
        # Fetch candidate files and their extracted text
        sql = """
            SELECT
                f.id, f.filename, f.relative_path, f.size_bytes, f.category,
                f.extension, f.modified_time, f.path, f.sha256,
                e.content_text, e.char_count
            FROM files f
            LEFT JOIN file_extractions e ON f.id = e.file_id
            WHERE f.project_id = ?
              AND f.size_bytes >= ?
              AND f.size_bytes <= ?
              AND f.category IN ('source', 'document', 'config', 'data')
            ORDER BY f.size_bytes ASC
        """
        candidates: List[Dict[str, Any]] = []

        with self.repo.db.session() as conn:
            cursor = conn.execute(sql, (project_id, self.min_file_size, self.max_file_size))
            rows = cursor.fetchall()

            for row in rows:
                fid = row["id"]
                if fid in excluded_file_ids:
                    continue

                rel_path = row["relative_path"] or ""
                # Check excluded directory patterns in path segments
                path_parts = set(Path(rel_path).parts)
                if path_parts & EXCLUDED_DIR_PATTERNS:
                    continue

                fname = (row["filename"] or "").lower()
                if any(fname.endswith(pat) for pat in SKIPPED_FILENAME_PATTERNS):
                    continue

                content = row["content_text"]
                # Fallback to reading file directly from disk if extraction was not stored or empty
                if not content:
                    fpath_str = row["path"]
                    if fpath_str:
                        try:
                            fpath = Path(fpath_str)
                            if fpath.exists() and fpath.is_file() and fpath.stat().st_size <= self.max_file_size:
                                content = fpath.read_text(encoding="utf-8", errors="replace")
                        except Exception:
                            content = None

                if not content or len(content.strip()) < self.min_file_size:
                    continue

                candidates.append({
                    "id": fid,
                    "filename": row["filename"],
                    "relative_path": row["relative_path"],
                    "size_bytes": row["size_bytes"],
                    "category": row["category"],
                    "extension": (row["extension"] or "").lower(),
                    "modified_time": row["modified_time"],
                    "path": row["path"],
                    "sha256": row["sha256"],
                    "text": content,
                    "text_len": len(content),
                })

        if len(candidates) < 2:
            return []

        # Group candidates into extension / language buckets
        buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for c in candidates:
            ext = c["extension"]
            bucket_key = EXTENSION_GROUPS.get(ext, ext or "other")
            buckets[bucket_key].append(c)

        # Candidate pairs matching threshold
        # (primary_file, variant_file, ratio)
        similar_pairs: List[Tuple[Dict[str, Any], Dict[str, Any], float]] = []
        comparisons_done = 0

        # Minimum length ratio to achieve >= 0.85 SequenceMatcher similarity:
        # 2 * len_a / (len_a + len_b) >= 0.85  =>  len_a / len_b >= 0.85 / (2 - 0.85) = 0.85 / 1.15 ≈ 0.739
        min_length_ratio = 0.735

        for bucket_name, bucket_files in buckets.items():
            if len(bucket_files) < 2:
                continue

            # Sort bucket by text length ascending
            bucket_files.sort(key=lambda x: x["text_len"])
            m = len(bucket_files)

            for i in range(m):
                file_a = bucket_files[i]
                len_a = file_a["text_len"]

                for j in range(i + 1, m):
                    if comparisons_done >= self.max_comparisons:
                        logger.warning(
                            f"Reached maximum comparison limit ({self.max_comparisons}) "
                            f"during duplicate detection for project {project_id}"
                        )
                        break

                    file_b = bucket_files[j]
                    len_b = file_b["text_len"]

                    # If length ratio is too small, similarity cannot mathematically reach min_similarity
                    if len_b > 0 and (len_a / len_b) < min_length_ratio:
                        # Since bucket_files is sorted by length, all subsequent j's will be even longer!
                        break

                    comparisons_done += 1

                    # Fast pre-check using SequenceMatcher heuristics
                    matcher = difflib.SequenceMatcher(None, file_a["text"], file_b["text"], autojunk=False)
                    if matcher.real_quick_ratio() < self.min_similarity:
                        continue
                    if matcher.quick_ratio() < self.min_similarity:
                        continue

                    # Full ratio calculation
                    ratio = matcher.ratio()
                    if ratio >= self.min_similarity:
                        # Determine which file is original/primary (older modified_time or shorter path)
                        mtime_a = file_a.get("modified_time") or ""
                        mtime_b = file_b.get("modified_time") or ""
                        if mtime_a and mtime_b and mtime_a <= mtime_b:
                            primary, variant = file_a, file_b
                        elif mtime_a and mtime_b and mtime_b < mtime_a:
                            primary, variant = file_b, file_a
                        else:
                            primary, variant = (file_a, file_b) if len(file_a["relative_path"]) <= len(file_b["relative_path"]) else (file_b, file_a)

                        similar_pairs.append((primary, variant, ratio))

                if comparisons_done >= self.max_comparisons:
                    break

        if not similar_pairs:
            return []

        # Cluster similar pairs around primary files
        # Map: primary_id -> {"primary": file_dict, "variants": [(variant_dict, ratio)]}
        cluster_map: Dict[str, Dict[str, Any]] = {}
        assigned_variants: Set[str] = set()

        # Sort pairs by similarity ratio descending so strongest matches claim variants first
        similar_pairs.sort(key=lambda p: p[2], reverse=True)

        for primary, variant, ratio in similar_pairs:
            # If variant is already assigned to a primary with higher or equal similarity, skip
            if variant["id"] in assigned_variants:
                continue

            # If primary was already assigned as a variant elsewhere, skip making it a primary
            if primary["id"] in assigned_variants:
                continue

            pid = primary["id"]
            if pid not in cluster_map:
                cluster_map[pid] = {
                    "primary": primary,
                    "variants": [],
                }

            cluster_map[pid]["variants"].append((variant, ratio))
            assigned_variants.add(variant["id"])

        # Format clusters
        similar_clusters: List[Dict[str, Any]] = []

        for pid, cdata in cluster_map.items():
            primary = cdata["primary"]
            variants_with_ratios = cdata["variants"]
            if not variants_with_ratios:
                continue

            ratios = [r for _, r in variants_with_ratios]
            avg_ratio = sum(ratios) / len(ratios)
            pct = int(round(avg_ratio * 100))
            # Reserve 100% for exact SHA-256 matches
            pct = min(pct, 99)

            primary_dict = {
                "id": primary["id"],
                "filename": primary["filename"],
                "relative_path": primary["relative_path"],
                "size_bytes": primary["size_bytes"],
                "category": primary["category"],
                "extension": primary["extension"],
                "modified_time": primary["modified_time"],
                "role": "original",
                "is_primary": True,
                "sha256": primary.get("sha256"),
            }

            variant_dicts: List[Dict[str, Any]] = []
            wasted_bytes = 0

            for variant, vratio in variants_with_ratios:
                vpct = min(int(round(vratio * 100)), 99)
                wasted_bytes += variant["size_bytes"]
                variant_dicts.append({
                    "id": variant["id"],
                    "filename": variant["filename"],
                    "relative_path": variant["relative_path"],
                    "size_bytes": variant["size_bytes"],
                    "category": variant["category"],
                    "extension": variant["extension"],
                    "modified_time": variant["modified_time"],
                    "role": "variant",
                    "is_primary": False,
                    "sha256": variant.get("sha256"),
                    "similarity_pct": vpct,
                })

            total_count = 1 + len(variant_dicts)
            diff_summary = (
                f"Very high similarity ({pct}%) — almost identical content with minor changes or comments"
                if pct >= 95
                else f"High similarity ({pct}%) — mostly matching code with slight modifications"
            )

            similar_clusters.append({
                "sha256": primary.get("sha256") or None,
                "count": total_count,
                "file_count": total_count,
                "size_bytes": primary["size_bytes"],
                "file_size": primary["size_bytes"],
                "wasted_bytes": wasted_bytes,
                "duplicate_type": "similar",
                "cluster_type": "similar",
                "similarity": round(avg_ratio, 4),
                "similarity_pct": pct,
                "difference_summary": diff_summary,
                "reason": f"{pct}% similar content with minor changes",
                "primary_file": primary_dict,
                "files": [primary_dict, *variant_dicts],
            })

        return similar_clusters
