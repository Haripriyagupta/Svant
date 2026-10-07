"""
AI Provider factory for SVANT Phase 3.
Manages provider resolution, lazy loading, and test overrides.
"""

from __future__ import annotations

from typing import Optional

from svant.config import settings
from svant.core.ai.base import AIProvider
from svant.core.ai.gemini import GeminiProvider
from svant.core.ai.mock import MockAIProvider
from svant.logger import get_logger

logger = get_logger("svant.core.ai.factory")

_active_ai_provider: Optional[AIProvider] = None


def get_ai_provider(provider_name: Optional[str] = None) -> Optional[AIProvider]:
    """
    Retrieve configured AI provider instance.
    Returns None if Local Only mode is active or no provider is configured.
    """
    global _active_ai_provider
    if _active_ai_provider is not None:
        return _active_ai_provider

    chosen = (provider_name or getattr(settings, "ai_provider", "none")).lower().strip()

    if chosen == "mock":
        return MockAIProvider()
    elif chosen == "gemini":
        return GeminiProvider()

    # If settings has gemini_api_key and local_only_mode is False, can default to Gemini if requested
    if getattr(settings, "gemini_api_key", None) and not getattr(settings, "local_only_mode", True):
        return GeminiProvider()

    return None


def set_active_ai_provider(provider: Optional[AIProvider]) -> None:
    """Override active provider (useful for test isolation)."""
    global _active_ai_provider
    _active_ai_provider = provider
