"""
Deterministic Mock AI Provider for offline testing and verification.
Records prompts and contexts received to verify privacy and secret redaction.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from svant.core.ai.base import AIGenerationResult, AIProvider
from svant.logger import get_logger

logger = get_logger("svant.core.ai.mock")


class MockAIProvider(AIProvider):
    """
    Mock AI Provider for tests.
    Generates deterministic grounded answers and records invocations for inspection.
    """

    def __init__(
        self,
        custom_response: Optional[str] = None,
        model_name: str = "mock-model-v1",
    ) -> None:
        self.custom_response = custom_response
        self._model_name = model_name
        self.call_history: List[Dict[str, Any]] = []

    @property
    def name(self) -> str:
        return "mock"

    @property
    def is_available(self) -> bool:
        return True

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        context: Optional[str] = None,
        **kwargs: Any,
    ) -> AIGenerationResult:
        # Record call for test verification
        record = {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "context": context or "",
            "kwargs": kwargs,
        }
        self.call_history.append(record)

        if self.custom_response:
            answer = self.custom_response
        else:
            # Generate deterministic answer synthesizing the context
            ctx_preview = (context[:120] + "...") if context and len(context) > 120 else (context or "No context")
            answer = (
                f"Based on the provided project context, here is the answer for '{user_prompt}':\n\n"
                f"Referenced information: {ctx_preview}"
            )

        return AIGenerationResult(
            text=answer,
            model_name=self._model_name,
            provider_name=self.name,
            metadata={"call_count": len(self.call_history)},
        )
