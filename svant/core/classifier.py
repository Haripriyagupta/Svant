"""
File classification system for SVANT.
Categorizes files by extension and MIME type into structured intelligence categories.
"""

from __future__ import annotations

import mimetypes
from enum import Enum
from pathlib import Path
from typing import NamedTuple


class FileCategory(str, Enum):
    SOURCE = "source"
    DOCUMENT = "document"
    CONFIG = "config"
    DATA = "data"
    BINARY = "binary"
    OTHER = "other"


# Extension sets
_SOURCE_EXTS = {
    ".py", ".pyw", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx",
    ".java", ".c", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".cs",
    ".go", ".rs", ".rb", ".php", ".swift", ".kt", ".kts", ".scala",
    ".html", ".htm", ".css", ".scss", ".sass", ".less", ".sql",
    ".sh", ".bash", ".zsh", ".ps1", ".bat", ".cmd", ".r", ".lua",
    ".pl", ".pm", ".dart", ".vue", ".svelte", ".zig", ".asm",
}

_DOCUMENT_EXTS = {
    ".pdf", ".docx", ".doc", ".txt", ".md", ".markdown", ".mdown",
    ".rtf", ".odt", ".csv", ".tsv", ".rst", ".tex",
}

_CONFIG_EXTS = {
    ".json", ".jsonc", ".yaml", ".yml", ".toml", ".ini", ".xml",
    ".env", ".conf", ".cfg", ".properties", ".lock", ".editorconfig",
    ".gitignore", ".gitattributes", ".dockerignore", ".npmrc",
}

_DATA_EXTS = {
    ".sqlite", ".sqlite3", ".db", ".parquet", ".avro", ".arrow",
    ".feather", ".hdf5", ".h5", ".xlsx", ".xls",
}

_BINARY_EXTS = {
    # Images
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp", ".tiff", ".svg",
    # Audio/Video
    ".mp3", ".wav", ".ogg", ".mp4", ".mov", ".avi", ".mkv", ".webm",
    # Executables & Libraries
    ".exe", ".dll", ".so", ".dylib", ".bin", ".o", ".a", ".class", ".pyc",
    # Archives
    ".zip", ".tar", ".gz", ".7z", ".rar", ".bz2", ".xz", ".iso",
}


class ClassificationResult(NamedTuple):
    category: FileCategory
    extension: str
    mime_type: str
    is_text_extractable: bool


class FileClassifier:
    """Classifies files based on name, extension, and content type."""

    @staticmethod
    def classify(path: Path | str) -> ClassificationResult:
        p = Path(path)
        ext = p.suffix.lower()
        # Handle dotfiles without traditional extension like .env or .gitignore
        name = p.name.lower()

        mime_type, _ = mimetypes.guess_type(str(p))
        if not mime_type:
            mime_type = "application/octet-stream"

        if ext in _SOURCE_EXTS:
            return ClassificationResult(
                category=FileCategory.SOURCE,
                extension=ext or name,
                mime_type=mime_type if mime_type != "application/octet-stream" else "text/plain",
                is_text_extractable=True,
            )

        if ext in _DOCUMENT_EXTS:
            return ClassificationResult(
                category=FileCategory.DOCUMENT,
                extension=ext or name,
                mime_type=mime_type,
                is_text_extractable=True,
            )

        if ext in _CONFIG_EXTS or name.startswith(".env") or name in {".gitignore", ".dockerignore", "dockerfile"}:
            return ClassificationResult(
                category=FileCategory.CONFIG,
                extension=ext or name,
                mime_type=mime_type if mime_type != "application/octet-stream" else "text/plain",
                is_text_extractable=True,
            )

        if ext in _DATA_EXTS:
            return ClassificationResult(
                category=FileCategory.DATA,
                extension=ext or name,
                mime_type=mime_type,
                is_text_extractable=False,
            )

        if ext in _BINARY_EXTS:
            return ClassificationResult(
                category=FileCategory.BINARY,
                extension=ext or name,
                mime_type=mime_type,
                is_text_extractable=False,
            )

        # Fallback check on MIME type
        if mime_type.startswith("text/"):
            return ClassificationResult(
                category=FileCategory.DOCUMENT,
                extension=ext or name,
                mime_type=mime_type,
                is_text_extractable=True,
            )

        return ClassificationResult(
            category=FileCategory.OTHER,
            extension=ext or name,
            mime_type=mime_type,
            is_text_extractable=False,
        )
