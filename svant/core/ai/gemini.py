"""
Gemini Cloud AI generation provider for SVANT Phase 3.
Invokes the Google Gemini REST API using lightweight, robust HTTP calls.
Sanitizes errors and never logs API keys.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
import httpx

from svant.config import settings
from svant.core.ai.base import AIGenerationResult, AIProvider
from svant.logger import get_logger

logger = get_logger("svant.core.ai.gemini")

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiProvider(AIProvider):
    """
    Cloud generation provider using Google Gemini API.
    Only invoked when Cloud AI is explicitly enabled and API key is configured.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
    ) -> None:
        self.api_key = api_key or getattr(settings, "gemini_api_key", None)
        self.model = model or getattr(settings, "gemini_model", "gemini-2.5-flash")
        self.timeout = timeout_seconds or getattr(settings, "ai_timeout_seconds", 30.0)

    @property
    def name(self) -> str:
        return "gemini"

    @property
    def is_available(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        context: Optional[str] = None,
        **kwargs: Any,
    ) -> AIGenerationResult:
        if not self.is_available:
            raise ValueError(
                "Gemini API key is not configured. Set SVANT_GEMINI_API_KEY in your environment or use Local Only mode."
            )

        url = f"{GEMINI_API_BASE}/{self.model}:generateContent"
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key.strip(),
        }

        # Build payload with system instructions and user message
        user_message_parts = []
        if context and context.strip():
            user_message_parts.append(f"PROJECT CONTEXT:\n{context.strip()}\n\n")
        user_message_parts.append(f"QUESTION:\n{user_prompt}")

        payload = {
            "system_instruction": {
                "parts": [{"text": system_prompt}]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": "".join(user_message_parts)}],
                }
            ],
            "generationConfig": {
                "temperature": kwargs.get("temperature", 0.2),
                "maxOutputTokens": kwargs.get("max_output_tokens", 2048),
            },
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, headers=headers, json=payload)

            if response.status_code == 200:
                data = response.json()
                candidates = data.get("candidates", [])
                if candidates:
                    content_parts = candidates[0].get("content", {}).get("parts", [])
                    if content_parts:
                        answer_text = content_parts[0].get("text", "")
                        return AIGenerationResult(
                            text=answer_text.strip(),
                            model_name=self.model,
                            provider_name=self.name,
                            metadata={"finish_reason": candidates[0].get("finishReason")},
                        )

                return AIGenerationResult(
                    text="Gemini returned an empty response. The content may have been flagged by safety filters.",
                    model_name=self.model,
                    provider_name=self.name,
                    metadata={"raw": data},
                )

            # Error handling without exposing API keys
            err_msg = f"Gemini API error (HTTP {response.status_code})"
            try:
                err_data = response.json()
                if "error" in err_data and "message" in err_data["error"]:
                    err_msg += f": {err_data['error']['message']}"
            except Exception:
                pass

            logger.error(f"Gemini API failure: {err_msg}")
            raise RuntimeError(err_msg)

        except httpx.TimeoutException as e:
            logger.warning(f"Gemini request timed out after {self.timeout}s")
            raise RuntimeError(f"Gemini request timed out after {self.timeout} seconds.") from e
        except httpx.RequestError as e:
            logger.error(f"Gemini connection error: {e}")
            raise RuntimeError(f"Failed to connect to Gemini API: {e}") from e
