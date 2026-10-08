"""
Resilience & Error Handling Tests for GeminiProvider (Phase 6 & 7).
Validates HTTP error handling, API timeout behavior, empty response handling,
and configuration checks without exposing credentials.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
import httpx

from svant.core.ai.gemini import GeminiProvider


def test_gemini_not_available_without_key():
    provider = GeminiProvider(api_key=None)
    assert not provider.is_available
    with pytest.raises(ValueError, match="Gemini API key is not configured"):
        provider.generate(system_prompt="sys", user_prompt="usr")


def test_gemini_successful_generation():
    provider = GeminiProvider(api_key="test-synthetic-key", timeout_seconds=5.0)
    assert provider.is_available

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": "Grounded project answer from Gemini."}]
                },
                "finishReason": "STOP",
            }
        ]
    }

    with patch("httpx.Client.post", return_value=mock_resp):
        res = provider.generate(system_prompt="sys", user_prompt="usr", context="ctx")
        assert res.text == "Grounded project answer from Gemini."
        assert res.provider_name == "gemini"
        assert res.metadata.get("finish_reason") == "STOP"


def test_gemini_http_error_does_not_expose_key():
    provider = GeminiProvider(api_key="secret-synthetic-key-123")
    mock_resp = MagicMock()
    mock_resp.status_code = 403
    mock_resp.json.return_value = {
        "error": {
            "code": 403,
            "message": "API key not valid. Please pass a valid API key.",
            "status": "PERMISSION_DENIED",
        }
    }

    with patch("httpx.Client.post", return_value=mock_resp):
        with pytest.raises(RuntimeError) as exc_info:
            provider.generate(system_prompt="sys", user_prompt="usr")
        err_msg = str(exc_info.value)
        assert "Gemini API error (HTTP 403)" in err_msg
        assert "secret-synthetic-key-123" not in err_msg


def test_gemini_timeout_handling():
    provider = GeminiProvider(api_key="test-key", timeout_seconds=1.0)
    with patch("httpx.Client.post", side_effect=httpx.TimeoutException("Connection timed out")):
        with pytest.raises(RuntimeError, match="timed out"):
            provider.generate(system_prompt="sys", user_prompt="usr")


def test_gemini_empty_response_fallback():
    provider = GeminiProvider(api_key="test-key")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"candidates": []}

    with patch("httpx.Client.post", return_value=mock_resp):
        res = provider.generate(system_prompt="sys", user_prompt="usr")
        assert "empty response" in res.text
