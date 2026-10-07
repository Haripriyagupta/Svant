"""
Local Secret Redaction Engine for SVANT Phase 3.
Sanitizes code, text, and metadata locally BEFORE context is sent to any external provider.
Ensures zero raw credentials leave the user's machine.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Set, Tuple

from svant.core.privacy.secrets import SECRET_PATTERNS
from svant.logger import get_logger

logger = get_logger("svant.core.privacy.redactor")


@dataclass
class RedactionResult:
    """Outcome of a text redaction pass."""

    sanitized_text: str
    redaction_count: int
    secret_types: List[str]


class SecretRedactor:
    """Detects and masks sensitive credentials from prompts and context snippets."""

    def __init__(self) -> None:
        self.patterns = SECRET_PATTERNS

    def redact(self, text: str) -> RedactionResult:
        """
        Scan text for all secret categories and replace with safe redaction markers.
        """
        if not text:
            return RedactionResult(sanitized_text="", redaction_count=0, secret_types=[])

        sanitized = text
        total_redactions = 0
        detected_types: Set[str] = set()

        # 1. Redact Private Keys (multiline block)
        if "PRIVATE_KEY" in self.patterns:
            matches = list(self.patterns["PRIVATE_KEY"].finditer(sanitized))
            if matches:
                total_redactions += len(matches)
                detected_types.add("PRIVATE_KEY")
                sanitized = self.patterns["PRIVATE_KEY"].sub("[REDACTED:PRIVATE_KEY]", sanitized)

        # 2. Redact Connection String Passwords
        if "CONNECTION_STRING" in self.patterns:
            def _replace_conn(m: Any) -> str:
                full = m.group(0)
                pwd = m.group(1)
                return full.replace(f":{pwd}@", ":[REDACTED:PASSWORD]@")

            subbed, count = self.patterns["CONNECTION_STRING"].subn(_replace_conn, sanitized)
            if count > 0:
                total_redactions += count
                detected_types.add("CONNECTION_STRING")
                sanitized = subbed

        # 3. Redact Key-Value Credential Assignments
        if "CREDENTIAL_ASSIGNMENT" in self.patterns:
            def _replace_cred(m: Any) -> str:
                var_name = m.group(1)
                quote = m.group(2)
                secret_val = m.group(3)
                # Keep variable name and quotes, redact the secret value
                return f"{var_name}={quote}[REDACTED:CREDENTIAL]{quote}"

            subbed, count = self.patterns["CREDENTIAL_ASSIGNMENT"].subn(_replace_cred, sanitized)
            if count > 0:
                total_redactions += count
                detected_types.add("CREDENTIAL_ASSIGNMENT")
                sanitized = subbed

        # 4. Redact Bearer Tokens
        if "BEARER_TOKEN" in self.patterns:
            def _replace_bearer(m: Any) -> str:
                return "Bearer [REDACTED:BEARER_TOKEN]"

            subbed, count = self.patterns["BEARER_TOKEN"].subn(_replace_bearer, sanitized)
            if count > 0:
                total_redactions += count
                detected_types.add("BEARER_TOKEN")
                sanitized = subbed

        # 5. Redact Platform Specific Tokens & JWTs
        for sec_type in ("AWS_KEY_ID", "GITHUB_TOKEN", "SLACK_TOKEN", "OPENAI_KEY", "GOOGLE_API_KEY", "JWT_TOKEN"):
            if sec_type in self.patterns:
                pattern = self.patterns[sec_type]
                subbed, count = pattern.subn(f"[REDACTED:{sec_type}]", sanitized)
                if count > 0:
                    total_redactions += count
                    detected_types.add(sec_type)
                    sanitized = subbed

        if total_redactions > 0:
            logger.info(f"Redacted {total_redactions} sensitive items of types {list(detected_types)} from text.")

        return RedactionResult(
            sanitized_text=sanitized,
            redaction_count=total_redactions,
            secret_types=sorted(list(detected_types)),
        )

    def redact_context_items(self, items: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
        """
        Sanitize a list of retrieved context chunk dictionaries in-place or returning copy.
        """
        sanitized_items = []
        total_redactions = 0

        for itm in items:
            copy_item = dict(itm)
            content = copy_item.get("content") or copy_item.get("snippet", "")
            res = self.redact(content)
            copy_item["content"] = res.sanitized_text
            copy_item["snippet"] = res.sanitized_text
            total_redactions += res.redaction_count
            sanitized_items.append(copy_item)

        return sanitized_items, total_redactions
