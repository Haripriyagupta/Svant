"""
AI Provider abstraction for SVANT Phase 3.
Defines the unified interface for local mock providers and cloud generation providers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, NamedTuple, Optional


@dataclass
class AIGenerationResult:
    """Standardized response from an AI generation provider."""

    text: str
    model_name: str
    provider_name: str
    metadata: Dict[str, Any]


class AIProvider(ABC):
    """Abstract base class for all SVANT AI generation providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier (e.g. 'gemini', 'mock', 'local')."""
        pass

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """Whether the provider is configured and ready for generation."""
        pass

    @abstractmethod
    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        context: Optional[str] = None,
        **kwargs: Any,
    ) -> AIGenerationResult:
        """
        Generate grounded text from system instruction, user query, and sanitized context.
        """
        pass
