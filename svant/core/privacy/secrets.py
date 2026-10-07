"""
High-confidence secret and credential detection patterns for SVANT Phase 3.
Prioritizes preventing leakage (false positives preferred over false negatives).
"""

from __future__ import annotations

import re
from typing import Dict, List, Pattern

# Compiled regular expressions for sensitive credential patterns
SECRET_PATTERNS: Dict[str, Pattern[str]] = {
    # 1. Private Cryptographic Keys
    "PRIVATE_KEY": re.compile(
        r"-----BEGIN (?:[A-Z0-9_-]+ )?PRIVATE KEY-----[\s\S]*?-----END (?:[A-Z0-9_-]+ )?PRIVATE KEY-----",
        re.MULTILINE,
    ),

    # 2. Key-Value credential assignments in code and configuration
    "CREDENTIAL_ASSIGNMENT": re.compile(
        r"""(?i)\b(api[_-]?key|api[_-]?secret|auth[_-]?token|access[_-]?token|secret[_-]?key|app[_-]?secret|private[_-]?key|client[_-]?secret|db[_-]?password|password|passwd|pwd)\b\s*[:=]\s*(['"]?)([\w\-.~+!@#$%^&*()]{4,})\2""",
    ),

    # 3. Connection Strings with embedded credentials
    "CONNECTION_STRING": re.compile(
        r"""\b(?:postgres|postgresql|mysql|mongodb(?:\+srv)?|redis|amqp|mssql)://[^\s:@/]+:([^\s:@/]+)@[^\s/]+""",
        re.IGNORECASE,
    ),

    # 4. Bearer Authentication Tokens
    "BEARER_TOKEN": re.compile(
        r"""(?i)\bBearer\s+([A-Za-z0-9_\-\.]{16,})\b""",
    ),

    # 5. Platform-specific API keys
    "AWS_KEY_ID": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "GITHUB_TOKEN": re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,}\b"),
    "SLACK_TOKEN": re.compile(r"\bxox[baprs]-[0-9a-zA-Z-]{20,}\b"),
    "OPENAI_KEY": re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}\b"),
    "GOOGLE_API_KEY": re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),

    # 6. JSON Web Tokens (JWT)
    "JWT_TOKEN": re.compile(
        r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"
    ),
}


def detect_secrets(text: str) -> List[str]:
    """Return names of secret types detected in text."""
    if not text:
        return []
    detected = []
    for name, pattern in SECRET_PATTERNS.items():
        if pattern.search(text):
            detected.append(name)
    return detected


def is_sensitive_value(value: str) -> bool:
    """Return True if the string contains sensitive credential patterns."""
    return bool(detect_secrets(value))


def redact_text(text: str) -> tuple[str, int]:
    """Quick helper to redact secrets using SecretRedactor."""
    from svant.core.privacy.redactor import SecretRedactor

    redactor = SecretRedactor()
    res = redactor.redact(text)
    return res.sanitized_text, res.redaction_count

