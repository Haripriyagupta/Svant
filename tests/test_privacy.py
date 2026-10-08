"""
Unit tests for SVANT local secret detection and redaction (Phase 3).
Verifies that sensitive tokens, keys, passwords, and credentials are scrubbed locally.
"""

import pytest
from svant.core.privacy.secrets import detect_secrets, redact_text, is_sensitive_value
from svant.core.privacy.redactor import SecretRedactor
from svant.core.rag.context import ContextItem


def test_redact_generic_api_keys():
    text = "api_key = 'abcdef1234567890abcdef1234567890'\nother_var = 123"
    redacted, count = redact_text(text)
    assert count >= 1
    assert "abcdef1234567890abcdef1234567890" not in redacted
    assert "[REDACTED:" in redacted
    assert "other_var = 123" in redacted


def test_redact_aws_access_key():
    text = "Deploying using AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE and region us-east-1"
    redacted, count = redact_text(text)
    assert count >= 1
    assert "AKIAIOSFODNN7EXAMPLE" not in redacted
    assert "[REDACTED:AWS_KEY_ID]" in redacted
    assert "region us-east-1" in redacted


def test_redact_github_tokens():
    token = "gh" + "p_" + "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    text = f"Pushing commit with {token}"
    redacted, count = redact_text(text)
    assert count >= 1
    assert token not in redacted
    assert "[REDACTED:GITHUB_TOKEN]" in redacted


def test_redact_bearer_token():
    text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdefghijklmnopqrstuvwxyz1234567890"
    redacted, count = redact_text(text)
    assert count >= 1
    assert "eyJhbGci" not in redacted
    assert "[REDACTED:BEARER_TOKEN]" in redacted or "[REDACTED:JWT_TOKEN]" in redacted


def test_redact_database_url_credentials():
    text = "DATABASE_URL=postgres://admin:SuperSecretPass123!@db.internal:5432/production"
    redacted, count = redact_text(text)
    assert count >= 1
    assert "SuperSecretPass123!" not in redacted
    assert "[REDACTED:PASSWORD]" in redacted
    assert "db.internal:5432/production" in redacted


def test_redact_private_key_pem():
    text = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEowIBAAKCAQEA0YqL9l5+8...fake...private...key...material...\n"
        "-----END RSA PRIVATE KEY-----"
    )
    redacted, count = redact_text(text)
    assert count >= 1
    assert "MIIEowIBAAKCAQEA0YqL9l5" not in redacted
    assert "[REDACTED:PRIVATE_KEY]" in redacted


def test_redact_slack_token():
    # Construct synthetic token at runtime so no literal token pattern exists in source code
    prefix = "xo" + "xb-"
    suffix = "synthetic-token-placeholder-12345"
    synthetic_slack_token = f"{prefix}{suffix}"
    text = f"SLACK_BOT_TOKEN={synthetic_slack_token}"
    redacted, count = redact_text(text)
    assert count >= 1
    assert synthetic_slack_token not in redacted
    assert "[REDACTED:SLACK_TOKEN]" in redacted


def test_redact_openai_key():
    token = "sk-" + "proj-" + "abcde123456789012345678901234567890123456789012345"
    text = f"OPENAI_API_KEY={token}"
    redacted, count = redact_text(text)
    assert count >= 1
    assert token not in redacted
    assert "[REDACTED:OPENAI_KEY]" in redacted


def test_detect_secrets_and_is_sensitive_value():
    assert is_sensitive_value("AKIA1234567890123456") is True
    assert is_sensitive_value("Just a normal sentence") is False
    test_gh_token = "gh" + "p_" + "123456789012345678901234567890123456"
    assert len(detect_secrets(test_gh_token)) >= 1


def test_preserves_innocent_code_and_text():
    innocent = (
        "def calculate_total(items):\n"
        "    tax_rate = 0.08\n"
        "    return sum(i.price for i in items) * (1 + tax_rate)\n"
        "This is documentation for the public API."
    )
    redacted, count = redact_text(innocent)
    assert count == 0
    assert redacted == innocent


def test_secret_redactor_context_item():
    redactor = SecretRedactor()
    item = ContextItem(
        file_id="f1",
        chunk_id="c1",
        filename="config.py",
        relative_path="config.py",
        project_id="p1",
        chunk_index=0,
        content="API_SECRET = 'secret_value_12345678901234567890'\nMAX_RETRIES = 3",
        relevance_score=0.9,
    )

    res = redactor.redact(item.content)
    assert res.redaction_count >= 1
    assert "secret_value_12345678901234567890" not in res.sanitized_text
    assert "[REDACTED:" in res.sanitized_text
    assert "MAX_RETRIES = 3" in res.sanitized_text
