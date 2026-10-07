"""
Configuration module for SVANT.
Loads settings from environment variables and .env with safe defaults.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional


def _load_env_file(dotenv_path: Path) -> None:
    """Lightweight .env parser that loads variables without third-party dependencies."""
    if not dotenv_path.is_file():
        return
    try:
        with open(dotenv_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("'\"")
                    if key and key not in os.environ:
                        os.environ[key] = val
    except Exception:
        pass


# Look for .env in project root or current working directory
_project_root = Path(__file__).resolve().parent.parent
_load_env_file(_project_root / ".env")


def _get_default_data_dir() -> Path:
    """
    Prefer D:\\SVANTData on Windows if D: drive exists,
    otherwise fallback to project-local data directory.
    """
    if os.name == "nt":
        d_drive = Path("D:/")
        if d_drive.exists():
            return Path("D:/SVANTData")
    # Fallback for environments where D: is not available
    return _project_root / "data"


class Settings:
    """SVANT Application Settings."""

    def __init__(self) -> None:
        self.app_name: str = "SVANT"
        self.version: str = "0.2.0"
        self.env: str = os.getenv("SVANT_ENV", "development")
        self.host: str = os.getenv("SVANT_HOST", "127.0.0.1")
        self.port: int = int(os.getenv("SVANT_PORT", "8000"))
        self.log_level: str = os.getenv("SVANT_LOG_LEVEL", "INFO").upper()

        # Data directory configuration
        raw_data_dir = os.getenv("SVANT_DATA_DIR")
        if raw_data_dir:
            self.data_dir: Path = Path(raw_data_dir).resolve()
        else:
            self.data_dir = _get_default_data_dir()

        self.db_path: Path = self.data_dir / "svant.db"
        self.log_dir: Path = self.data_dir / "logs"
        self.models_dir: Path = self.data_dir / "models"
        self.indexes_dir: Path = self.data_dir / "indexes"

        # Scanning and extraction limits
        self.max_extract_size_mb: int = int(os.getenv("SVANT_MAX_EXTRACT_SIZE_MB", "15"))

        # Phase 2 Local Intelligence Settings
        self.embedding_model: str = os.getenv("SVANT_EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
        self.embedding_batch_size: int = int(os.getenv("SVANT_EMBEDDING_BATCH_SIZE", "32"))
        self.chunk_size: int = int(os.getenv("SVANT_CHUNK_SIZE", "500"))
        self.chunk_overlap: int = int(os.getenv("SVANT_CHUNK_OVERLAP", "50"))
        self.hybrid_semantic_weight: float = float(os.getenv("SVANT_HYBRID_SEMANTIC_WEIGHT", "0.6"))
        self.hybrid_keyword_weight: float = float(os.getenv("SVANT_HYBRID_KEYWORD_WEIGHT", "0.4"))

        raw_exclusions = os.getenv(
            "SVANT_EXCLUDED_DIRS",
            ".git,.venv,venv,node_modules,dist,build,__pycache__,.pytest_cache,.idea,.vscode,.mypy_cache",
        )
        self.excluded_dirs: List[str] = [
            item.strip() for item in raw_exclusions.split(",") if item.strip()
        ]

        # Privacy & Security
        self.local_only_mode: bool = (
            os.getenv("SVANT_LOCAL_ONLY_MODE", "true").lower() in ("true", "1", "yes")
        )

        # Future Phase Placeholders (Inactive in Phase 1)
        self.gemini_api_key: Optional[str] = os.getenv("GEMINI_API_KEY")

    def ensure_directories(self) -> None:
        """Create persistent storage directories if they do not exist."""
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self.log_dir.mkdir(parents=True, exist_ok=True)
            self.models_dir.mkdir(parents=True, exist_ok=True)
            self.indexes_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            # If default path failed (e.g. permission or missing drive), fallback to local data dir
            local_fallback = _project_root / "data"
            local_fallback.mkdir(parents=True, exist_ok=True)
            self.data_dir = local_fallback
            self.db_path = self.data_dir / "svant.db"
            self.log_dir = self.data_dir / "logs"
            self.models_dir = self.data_dir / "models"
            self.indexes_dir = self.data_dir / "indexes"
            self.log_dir.mkdir(parents=True, exist_ok=True)
            self.models_dir.mkdir(parents=True, exist_ok=True)
            self.indexes_dir.mkdir(parents=True, exist_ok=True)


# Singleton settings instance
settings = Settings()
