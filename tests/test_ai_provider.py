"""
Unit tests for AI Provider abstractions (Phase 3).
Verifies provider contracts, MockAIProvider deterministic output, and Gemini configuration handling.
"""

import pytest
from svant.core.ai.base import AIProvider, AIGenerationResult
from svant.core.ai.mock import MockAIProvider
from svant.core.ai.gemini import GeminiProvider
from svant.core.ai.factory import get_ai_provider, set_active_ai_provider


def test_mock_provider_generation_with_context():
    provider = MockAIProvider()
    assert provider.is_available is True
    assert provider.name == "mock"

    context_str = "DEFAULT_PORT = 8000\nDATABASE_FILE = 'svant.db'"

    res = provider.generate(
        system_prompt="You are a grounded assistant.",
        user_prompt="What is DEFAULT_PORT?",
        context=context_str,
    )

    assert isinstance(res, AIGenerationResult)
    assert res.provider_name == "mock"
    assert "Based on the provided project context" in res.text
    assert "DEFAULT_PORT" in res.text


def test_mock_provider_generation_without_context():
    provider = MockAIProvider()
    res = provider.generate(
        system_prompt="You are a grounded assistant.",
        user_prompt="Explain quantum gravity",
        context=None,
    )
    assert "Based on the provided project context" in res.text or len(res.text) > 0


def test_gemini_provider_unconfigured():
    provider = GeminiProvider(api_key=None)
    assert provider.is_available is False

    with pytest.raises(ValueError) as exc_info:
        provider.generate(
            system_prompt="System instructions",
            user_prompt="Hello",
            context=None,
        )
    assert "API key is not configured" in str(exc_info.value)


def test_provider_factory():
    # Test getting mock provider
    mock = get_ai_provider("mock")
    assert isinstance(mock, MockAIProvider)

    # Test getting gemini provider
    gemini = get_ai_provider("gemini")
    assert isinstance(gemini, GeminiProvider)

    # Test custom override
    custom_mock = MockAIProvider()
    set_active_ai_provider(custom_mock)
    assert get_ai_provider() is custom_mock
    # Reset
    set_active_ai_provider(None)
