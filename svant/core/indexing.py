"""
Incremental indexing pipeline for SVANT Phase 2.
Coordinates text extraction, intelligent chunking, batch embedding generation,
authoritative SQLite chunk storage, and FAISS vector indexing.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Callable, Dict, List, NamedTuple, Optional, Set

import numpy as np

from svant.config import settings
from svant.core.chunker import TextChunker, TextChunk
from svant.core.embeddings import EmbeddingProvider, get_embedding_provider
from svant.core.extractor import DocumentExtractor
from svant.core.vector_store import FAISSVectorStore, get_project_index_path
from svant.db.repository import Repository
from svant.logger import get_logger

logger = get_logger("svant.core.indexing")


class IndexSummary(NamedTuple):
    project_id: str
    total_files: int
    indexed_files: int
    skipped_files: int
    failed_files: int
    total_chunks: int
    total_vectors: int
    duration_seconds: float


class IndexingPipeline:
    """
    Coordinates local vector indexing of tracked project files.
    Skips unchanged files using SHA-256 content hashes for high performance.
    """

    def __init__(
        self,
        repo: Repository,
        embedding_provider: Optional[EmbeddingProvider] = None,
        chunker: Optional[TextChunker] = None,
        extractor: Optional[DocumentExtractor] = None,
    ) -> None:
        self.repo = repo
        self.embedding_provider = embedding_provider or get_embedding_provider()
        self.chunker = chunker or TextChunker()
        self.extractor = extractor or DocumentExtractor()

    def index_project(
        self,
        project_id: str,
        force_rebuild: bool = False,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> IndexSummary:
        """
        Incrementally index all extractable files in a project.
        If force_rebuild=True, purges existing vector store and chunks before indexing.
        """
        start_time = datetime.datetime.now(datetime.timezone.utc)
        project = self.repo.get_project(project_id)
        if not project:
            raise ValueError(f"Project with ID '{project_id}' not found.")

        index_path = get_project_index_path(project_id)
        vector_store = FAISSVectorStore(
            dimension=self.embedding_provider.dimension,
            index_path=index_path,
        )

        if force_rebuild:
            logger.info(f"Force rebuilding vector index for project '{project['name']}' ({project_id})")
            # Drop existing chunks and reset FAISS
            self.repo.delete_chunks_by_project(project_id)
            vector_store.reset()

        self.repo.upsert_project_index_status(
            project_id=project_id,
            status="indexing",
            model_name=self.embedding_provider.model_name,
            dimension=self.embedding_provider.dimension,
        )

        # Retrieve all tracked files for this project
        files = self.repo.list_files(project_id=project_id, limit=100000)
        total_files = len(files)

        indexed_files = 0
        skipped_files = 0
        failed_files = 0

        # Discover active files to clean up deleted/stale chunks
        active_file_ids: Set[str] = {f["id"] for f in files}
        existing_chunks = self.repo.get_chunks_by_project(project_id)
        chunk_file_ids = {c["file_id"] for c in existing_chunks}
        stale_file_ids = chunk_file_ids - active_file_ids

        for stale_fid in stale_file_ids:
            stale_vids = self.repo.delete_chunks_by_file(stale_fid)
            if stale_vids:
                vector_store.remove_vectors(stale_vids)

        existing_vids: Set[int] = vector_store.get_all_vector_ids()

        for idx, file_rec in enumerate(files, start=1):
            file_id = file_rec["id"]
            file_path = file_rec["path"]
            filename = file_rec["filename"]
            rel_path = file_rec["relative_path"]
            category = file_rec["category"]
            file_sha256 = file_rec.get("sha256")

            # Check if file already has chunks and if hash is unchanged AND all vectors exist in FAISS
            current_file_chunks = self.repo.get_chunks_by_file(file_id)
            chunks_in_vector_store = (
                bool(current_file_chunks)
                and (vector_store.count() > 0)
                and all(c["vector_id"] in existing_vids for c in current_file_chunks)
            )

            if (
                not force_rebuild
                and current_file_chunks
                and chunks_in_vector_store
                and file_sha256
                and current_file_chunks[0].get("sha256") == file_sha256
            ):
                skipped_files += 1
                if progress_callback:
                    progress_callback(idx, total_files, f"Skipped (unchanged): {filename}")
                continue

            # Need to extract or read existing extraction
            extraction = self.repo.get_extraction(file_id)
            text_content: Optional[str] = None

            if extraction and extraction.get("status") == "extracted" and extraction.get("content_text"):
                text_content = extraction["content_text"]
            else:
                # Attempt extraction if extractable
                if Path(file_path).is_file():
                    ext_res = self.extractor.extract(file_path)
                    if ext_res.status == "extracted" and ext_res.text:
                        text_content = ext_res.text
                        self.repo.upsert_extraction(
                            file_id=file_id,
                            project_id=project_id,
                            content_text=ext_res.text,
                            char_count=ext_res.char_count,
                            status=ext_res.status,
                            error_message=ext_res.error,
                        )

            if not text_content:
                # File is not extractable (e.g. binary or empty)
                if current_file_chunks:
                    old_vids = self.repo.delete_chunks_by_file(file_id)
                    vector_store.remove_vectors(old_vids)
                    existing_vids.difference_update(old_vids)
                skipped_files += 1
                continue

            try:
                # 1. Chunk document text
                chunks = self.chunker.chunk_document(
                    project_id=project_id,
                    file_id=file_id,
                    relative_path=rel_path,
                    filename=filename,
                    text=text_content,
                    category=category,
                )

                if not chunks:
                    if current_file_chunks:
                        old_vids = self.repo.delete_chunks_by_file(file_id)
                        vector_store.remove_vectors(old_vids)
                        existing_vids.difference_update(old_vids)
                    skipped_files += 1
                    continue

                # 2. Clean out old chunks and FAISS vectors for this file before replacing
                if current_file_chunks:
                    old_vids = self.repo.delete_chunks_by_file(file_id)
                    vector_store.remove_vectors(old_vids)
                    existing_vids.difference_update(old_vids)

                # 3. Generate embeddings
                chunk_texts = [c.text for c in chunks]
                embeddings_matrix = self.embedding_provider.embed_texts(chunk_texts)

                # 4. Insert chunks into SQLite and receive assigned vector_ids
                chunk_dicts = [
                    {
                        "id": c.chunk_id,
                        "project_id": project_id,
                        "file_id": file_id,
                        "chunk_index": c.chunk_index,
                        "text": c.text,
                        "char_count": c.char_count,
                        "word_count": c.word_count,
                        "content_type": c.content_type,
                        "metadata": c.metadata,
                        "sha256": file_sha256,
                    }
                    for c in chunks
                ]
                assigned_vids = self.repo.insert_chunks(chunk_dicts)

                # 5. Add vectors to FAISS index
                vector_store.add_vectors(assigned_vids, embeddings_matrix)
                existing_vids.update(assigned_vids)

                indexed_files += 1
                self.repo.update_file_index_status(file_id, "indexed")

            except Exception as err:
                logger.warning(f"Error indexing file '{filename}' ({file_path}): {err}")
                failed_files += 1
                self.repo.update_file_index_status(file_id, "failed")

            if progress_callback:
                progress_callback(idx, total_files, f"Indexed: {filename}")

        # Save updated FAISS index to disk
        vector_store.save()

        end_time = datetime.datetime.now(datetime.timezone.utc)
        duration = (end_time - start_time).total_seconds()
        now_iso = end_time.isoformat()

        total_chunks = self.repo.count_chunks_by_project(project_id)
        total_vectors = vector_store.count()

        final_status = "indexed" if failed_files == 0 or indexed_files > 0 else "failed"

        self.repo.upsert_project_index_status(
            project_id=project_id,
            status=final_status,
            model_name=self.embedding_provider.model_name,
            dimension=self.embedding_provider.dimension,
            total_chunks=total_chunks,
            total_vectors=total_vectors,
            last_indexed_at=now_iso,
        )

        logger.info(
            f"Indexing completed for '{project['name']}': {indexed_files} indexed, "
            f"{skipped_files} skipped, {failed_files} failed, "
            f"{total_chunks} chunks ({total_vectors} vectors) in {duration:.2f}s"
        )

        return IndexSummary(
            project_id=project_id,
            total_files=total_files,
            indexed_files=indexed_files,
            skipped_files=skipped_files,
            failed_files=failed_files,
            total_chunks=total_chunks,
            total_vectors=total_vectors,
            duration_seconds=duration,
        )
