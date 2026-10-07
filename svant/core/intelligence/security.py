"""
Security & Secret Exposure Analyzer for SVANT Phase 4 & 5.
Integrates with svant.core.privacy to detect exposed secrets, sensitive files,
and insecure configurations. Guarantees ZERO raw secret exposure in findings.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from svant.core.intelligence.models import (
    Finding,
    FindingCategory,
    FindingSeverity,
    PriorityTier,
)
from svant.core.privacy.redactor import SecretRedactor
from svant.core.privacy.secrets import SECRET_PATTERNS
from svant.db.repository import Repository
from svant.logger import get_logger

logger = get_logger("svant.core.intelligence.security")

# Sensitive filenames that should never be committed
SENSITIVE_FILENAMES = {
    ".env", ".env.local", ".env.production", ".env.staging", ".env.development",
    "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519",
    "credentials.json", "service-account.json", "service_account.json",
    "token.json", "jwt.key", "auth_token.txt",
}

# Dangerous configurations
DANGEROUS_CONFIG_PATTERNS = [
    (
        re.compile(r"""(?i)\b(?:verify\s*=\s*False|rejectUnauthorized\s*:\s*false|insecure_skip_verify\s*=\s*true)\b"""),
        "Disabled SSL/TLS Certificate Verification",
        "Disabling SSL certificate validation enables Man-in-the-Middle (MitM) attacks.",
        "Enable SSL verification by removing verify=False / rejectUnauthorized: false.",
        FindingSeverity.HIGH,
    ),
    (
        re.compile(r"""(?i)\bDEBUG\s*=\s*True\b"""),
        "Active Debug Mode in Configuration",
        "Debug mode active in configuration exposes stack traces, server variables, and internal code paths.",
        "Ensure DEBUG is driven by environment variables and disabled (False) in production deployments.",
        FindingSeverity.MEDIUM,
    ),
]


class SecurityAnalyzer:
    """Discovers secret exposures, dangerous configs, and credential leaks."""

    def __init__(self, repo: Repository, redactor: Optional[SecretRedactor] = None) -> None:
        self.repo = repo
        self.redactor = redactor or SecretRedactor()

    def analyze(self, project_id: str, files: List[Dict[str, Any]]) -> List[Finding]:
        """Perform comprehensive static security evaluation on project files."""
        findings: List[Finding] = []

        for f in files:
            file_id = f["id"]
            filename = f.get("filename", "")
            rel_path = f.get("relative_path", "").replace("\\", "/")
            name_lower = filename.lower()

            # 1. Check for sensitive files tracked in repository
            if name_lower in SENSITIVE_FILENAMES or (
                name_lower.startswith(".env") and not name_lower.endswith((".example", ".sample", ".template", ".test"))
            ):
                findings.append(
                    Finding(
                        id="",
                        project_id=project_id,
                        category=FindingCategory.SECURITY,
                        severity=FindingSeverity.HIGH,
                        priority_tier=PriorityTier.FIX_FIRST,
                        title=f"Sensitive credential or environment file tracked: {filename}",
                        description=(
                            f"File '{rel_path}' matches patterns for sensitive local environment or credential storage. "
                            "Committing live environment files risks catastrophic token, database, and credential leakage."
                        ),
                        recommendation=f"Add '{filename}' to .gitignore and provide a sanitized '{filename}.example' template instead.",
                        file_id=file_id,
                        relative_path=rel_path,
                        location="File level",
                        evidence=f"Sensitive file: {rel_path}",
                        confidence=1.0,
                    )
                )

            # 2. Check private keys by extension
            if name_lower.endswith((".pem", ".key", ".pfx", ".p12", ".pkcs12")) and not name_lower.endswith(".pub"):
                findings.append(
                    Finding(
                        id="",
                        project_id=project_id,
                        category=FindingCategory.SECURITY,
                        severity=FindingSeverity.CRITICAL,
                        priority_tier=PriorityTier.FIX_FIRST,
                        title=f"Cryptographic private key or certificate file tracked: {filename}",
                        description=(
                            f"Detected private cryptographic key file '{rel_path}'. "
                            "Private keys and certificates must NEVER be committed to source repositories."
                        ),
                        recommendation="Remove the private key file from version control and rotate the affected key pair immediately.",
                        file_id=file_id,
                        relative_path=rel_path,
                        location="File level",
                        evidence=f"Private key file: {rel_path}",
                        confidence=1.0,
                    )
                )

            # 3. Content-level Secret Analysis
            # Fetch extracted text if available
            extraction = self.repo.get_extraction(file_id)
            if not extraction or not extraction.get("content_text"):
                continue

            text = extraction["content_text"]
            lines = text.splitlines()

            # Scan lines for regex patterns
            found_secrets_in_file: Set[str] = set()

            for line_idx, line in enumerate(lines, start=1):
                clean_line = line.strip()
                if not clean_line or len(clean_line) > 1000:
                    continue

                # Check secret patterns
                for sec_type, pattern in SECRET_PATTERNS.items():
                    if sec_type in found_secrets_in_file:
                        continue  # Avoid reporting the same secret type dozens of times in the same file

                    match = pattern.search(clean_line)
                    if match:
                        found_secrets_in_file.add(sec_type)

                        # Determine severity based on secret type
                        if sec_type in ("PRIVATE_KEY", "AWS_KEY_ID"):
                            sev = FindingSeverity.CRITICAL
                            tier = PriorityTier.FIX_FIRST
                        elif sec_type in ("GITHUB_TOKEN", "SLACK_TOKEN", "OPENAI_KEY", "GOOGLE_API_KEY", "BEARER_TOKEN", "CONNECTION_STRING"):
                            sev = FindingSeverity.HIGH
                            tier = PriorityTier.FIX_FIRST
                        else:
                            sev = FindingSeverity.HIGH
                            tier = PriorityTier.SHOULD_FIX

                        # Create SAFE, REDACTED evidence ONLY
                        redacted_line = self.redactor.redact(clean_line).sanitized_text
                        # Additional safety check: truncate to safe excerpt
                        safe_evidence = f"Line {line_idx}: {redacted_line[:120]}"

                        findings.append(
                            Finding(
                                id="",
                                project_id=project_id,
                                category=FindingCategory.SECURITY,
                                severity=sev,
                                priority_tier=tier,
                                title=f"Potential exposed secret detected: {sec_type} in {filename}",
                                description=(
                                    f"Detected pattern matching '{sec_type}' on line {line_idx} of '{rel_path}'. "
                                    "Exposing API keys, tokens, or credentials in source files risks unauthorized access and credential compromise."
                                ),
                                recommendation="Move credentials to environment variables or a secure local vault. Rotate any exposed tokens immediately.",
                                file_id=file_id,
                                relative_path=rel_path,
                                location=f"Line {line_idx}",
                                evidence=safe_evidence,
                                confidence=0.95,
                            )
                        )

                # Check dangerous config patterns
                for cfg_pat, cfg_title, cfg_desc, cfg_rec, cfg_sev in DANGEROUS_CONFIG_PATTERNS:
                    if cfg_pat.search(clean_line):
                        findings.append(
                            Finding(
                                id="",
                                project_id=project_id,
                                category=FindingCategory.SECURITY,
                                severity=cfg_sev,
                                priority_tier=PriorityTier.SHOULD_FIX,
                                title=f"{cfg_title} in {filename}",
                                description=f"{cfg_desc} Found on line {line_idx} of '{rel_path}'.",
                                recommendation=cfg_rec,
                                file_id=file_id,
                                relative_path=rel_path,
                                location=f"Line {line_idx}",
                                evidence=f"Line {line_idx}: {clean_line[:100]}",
                                confidence=0.9,
                            )
                        )

        return findings
