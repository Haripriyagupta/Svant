"""
Structured logging module for SVANT.
Ensures sensitive tokens, passwords, and API keys are never exposed in log output.
"""

from __future__ import annotations

import logging
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from svant.config import settings

# Regex patterns matching potential secrets to sanitize
_REDACTION_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|password|passwd|token|auth|credential)[\s:=]+['\"]?([^\s'\";,]{4,})['\"]?"),
    re.compile(r"AIza[0-9A-Za-z\-_]{35}"),  # Google API keys
    re.compile(r"sk-[a-zA-Z0-9_\-]{20,}"),  # Common OpenAI / provider token patterns
    re.compile(r"(?i)bearer\s+[a-zA-Z0-9_\-\.]{15,}"),
]


class RedactingFormatter(logging.Formatter):
    """Log formatter that automatically masks sensitive tokens and secrets."""

    def format(self, record: logging.LogRecord) -> str:
        original = super().format(record)
        redacted = original
        for pattern in _REDACTION_PATTERNS:
            def _mask(match: re.Match[str]) -> str:
                full = match.group(0)
                # Keep the prefix (e.g. "api_key: ") and mask the secret part
                if len(match.groups()) >= 2 and match.group(2):
                    secret = match.group(2)
                    return full.replace(secret, "[REDACTED]")
                return "[REDACTED]"
            redacted = pattern.sub(_mask, redacted)
        return redacted


_logger: Optional[logging.Logger] = None


def get_logger(name: str = "svant") -> logging.Logger:
    """Return a configured logger instance with redacting formatters."""
    global _logger
    if _logger is not None:
        return logging.getLogger(name)

    settings.ensure_directories()
    root_logger = logging.getLogger("svant")
    log_level = getattr(logging, settings.log_level, logging.INFO)
    root_logger.setLevel(log_level)

    # Avoid duplicate handlers if already configured
    if not root_logger.handlers:
        formatter = RedactingFormatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

        # File handler (Rotating, max 10MB per file, 3 backups)
        try:
            log_file = settings.log_dir / "svant.log"
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=10 * 1024 * 1024,
                backupCount=3,
                encoding="utf-8",
            )
            file_handler.setLevel(log_level)
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
        except Exception as e:
            root_logger.warning(f"Could not initialize log file handler: {e}")

    _logger = root_logger
    return logging.getLogger(name)
