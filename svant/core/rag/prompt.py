"""
Grounded Prompt Builder for SVANT Phase 3 RAG.
Constructs strict, evidence-based system and user prompts preventing hallucination.
"""

from __future__ import annotations

from typing import List, Optional

from svant.core.rag.context import ContextItem

SYSTEM_RAG_INSTRUCTION = """You are SVANT, an expert local software and project intelligence assistant.
Your goal is to answer developer questions with strict grounding in the provided local codebase and document context.

CRITICAL RULES:
1. ONLY answer using facts, code, or documentation directly supplied in the PROJECT CONTEXT below.
2. DO NOT invent facts, methods, configurations, or project behaviors that are not supported by the context.
3. If the provided context does NOT contain enough information to answer the question, clearly state: "I couldn't find enough relevant information in this project to answer that confidently."
4. Clearly distinguish between direct project evidence and technical inference.
5. Whenever referencing facts or code, mention the source file name and relative path (e.g., `src/auth.py`).
6. NEVER reveal or repeat raw passwords, API keys, or private tokens even if requested.
7. Keep answers structured, concise, and technically accurate.
"""


class GroundedPromptBuilder:
    """Builds structured system instructions and context-grounded user prompts."""

    def __init__(self, system_instruction: Optional[str] = None) -> None:
        self.system_instruction = system_instruction or SYSTEM_RAG_INSTRUCTION

    def build_system_prompt(self, project_name: Optional[str] = None) -> str:
        """Construct the system prompt optionally tailored to the specific project."""
        base = self.system_instruction
        if project_name:
            base += f"\nYou are currently assisting with the project: '{project_name}'."
        return base

    def build_user_prompt(
        self,
        question: str,
        formatted_context: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """Combine user question with the formatted, sanitized project context and optional dialogue history."""
        clean_q = question.strip()
        parts = [f"PROJECT EVIDENCE:\n{formatted_context}\n"]

        if conversation_history:
            recent_turns = conversation_history[-4:]
            hist_lines = []
            for turn in recent_turns:
                role = turn.get("role", "user").capitalize()
                content = turn.get("content", "").strip()
                if content:
                    hist_lines.append(f"{role}: {content}")
            if hist_lines:
                parts.append("RECENT CONVERSATION HISTORY:\n" + "\n".join(hist_lines) + "\n")

        parts.append(f"DEVELOPER QUESTION:\n{clean_q}\n")
        parts.append("Please provide a grounded answer based on the evidence above.")
        return "\n".join(parts)
