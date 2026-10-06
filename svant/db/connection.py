"""
SQLite Connection Manager for SVANT.
Configures robust SQLite pragmas (WAL, foreign keys, busy timeout).
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

from svant.config import settings
from svant.logger import get_logger

logger = get_logger("svant.db")


class DatabaseManager:
    """Manages SQLite database connections and initialization."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        if db_path is not None:
            self.db_path = Path(db_path)
        else:
            settings.ensure_directories()
            self.db_path = settings.db_path

        # If not memory, ensure parent directory exists
        if str(self.db_path) != ":memory:":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def get_connection(self) -> sqlite3.Connection:
        """Create and configure a new SQLite connection."""
        conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,
            timeout=10.0,
        )
        conn.row_factory = sqlite3.Row

        # Essential pragmas for concurrency, integrity, and performance
        conn.execute("PRAGMA foreign_keys = ON;")
        if str(self.db_path) != ":memory:":
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA busy_timeout = 5000;")
        return conn

    @contextmanager
    def session(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager providing a transactional connection."""
        conn = self.get_connection()
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error during transaction rollback: {e}")
            raise
        finally:
            conn.close()


# Default application database manager instance
_default_manager: Optional[DatabaseManager] = None


def get_db(db_path: Optional[Path] = None) -> DatabaseManager:
    """Get or initialize the database manager."""
    global _default_manager
    if db_path is not None:
        return DatabaseManager(db_path)
    if _default_manager is None:
        _default_manager = DatabaseManager()
    return _default_manager
