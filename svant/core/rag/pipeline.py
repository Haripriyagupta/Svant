"""
Complete RAG Pipeline orchestrator for SVANT Phase 3.
Coordinates retrieval, deduplication, local secret redaction, grounded prompt creation,
AI generation (Gemini, Mock, or Local-Only), and citation generation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

from svant.config import settings
from svant.core.ai.base import AIProvider
from svant.core.ai.factory import get_ai_provider
from svant.core.privacy.redactor import SecretRedactor
from svant.core.rag.citations import Citation, CitationGenerator
from svant.core.rag.context import ContextAssembler, ContextItem
from svant.core.rag.prompt import GroundedPromptBuilder
from svant.core.search import SearchMode, SearchService
from svant.db.repository import Repository
from svant.logger import get_logger

logger = get_logger("svant.core.rag.pipeline")


@dataclass
class RAGResponse:
    """Standardized response contract for grounded AI chat queries."""

    answer: str
    provider: str
    mode: str
    sources: List[Citation]
    context_count: int
    redactions: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "answer": self.answer,
            "provider": self.provider,
            "mode": self.mode,
            "sources": [s.to_dict() for s in self.sources],
            "context_count": self.context_count,
            "redactions": self.redactions,
        }


class RAGPipeline:
    """End-to-end grounded retrieval-augmented generation engine."""

    def __init__(
        self,
        repo: Repository,
        search_service: Optional[SearchService] = None,
        ai_provider: Optional[AIProvider] = None,
        redactor: Optional[SecretRedactor] = None,
        assembler: Optional[ContextAssembler] = None,
        prompt_builder: Optional[GroundedPromptBuilder] = None,
    ) -> None:
        self.repo = repo
        self.search_service = search_service or SearchService(repo)
        self.ai_provider = ai_provider
        self.redactor = redactor or SecretRedactor()
        self.assembler = assembler or ContextAssembler()
        self.prompt_builder = prompt_builder or GroundedPromptBuilder()

    def query(
        self,
        project_id: str,
        message: str,
        search_mode: SearchMode = SearchMode.HYBRID,
        top_k: Optional[int] = None,
        provider_name: Optional[str] = None,
    ) -> RAGResponse:
        """
        Execute grounded RAG workflow for a user question.
        """
        clean_msg = message.strip()
        if not clean_msg:
            return RAGResponse(
                answer="Please enter a question about your project.",
                provider="none",
                mode=search_mode.value,
                sources=[],
                context_count=0,
                redactions=0,
            )

        # 1. Validate project
        project = self.repo.get_project(project_id)
        if not project:
            raise ValueError(f"Project '{project_id}' not found.")

        # 2. Local Privacy & Redaction on user question
        user_q_redact = self.redactor.redact(clean_msg)
        sanitized_question = user_q_redact.sanitized_text
        total_redactions = user_q_redact.redaction_count

        # 3. Local Retrieval (Phase 2 SearchService)
        fetch_k = top_k or self.assembler.top_k
        logger.debug(f"Retrieving {fetch_k} candidates for query '{clean_msg}' in mode '{search_mode.value}'")
        search_hits = self.search_service.search(
            query=clean_msg,
            project_id=project_id,
            mode=search_mode,
            limit=fetch_k,
        )

        # 4. Context Assembly & Deduplication
        raw_items = self.assembler.assemble(search_hits, project_id=project_id)

        # Handle Empty Retrieval
        if not raw_items:
            logger.info(f"No relevant context found for project '{project['name']}' on query '{clean_msg}'")
            return RAGResponse(
                answer=(
                    f"I couldn't find enough relevant information in '{project['name']}' to answer that confidently. "
                    "You may want to verify that the project is indexed, or try asking a more specific question."
                ),
                provider="local",
                mode=search_mode.value,
                sources=[],
                context_count=0,
                redactions=total_redactions,
            )

        # 5. Local Privacy & Secret Redaction on retrieved chunks
        sanitized_items: List[ContextItem] = []

        for itm in raw_items:
            redact_res = self.redactor.redact(itm.content)
            total_redactions += redact_res.redaction_count
            sanitized_item = ContextItem(
                file_id=itm.file_id,
                chunk_id=itm.chunk_id,
                filename=itm.filename,
                relative_path=itm.relative_path,
                project_id=itm.project_id,
                chunk_index=itm.chunk_index,
                content=redact_res.sanitized_text,
                relevance_score=itm.relevance_score,
                line_start=itm.line_start,
                line_end=itm.line_end,
                section=itm.section,
            )
            sanitized_items.append(sanitized_item)

        # 6. Generate Citations
        citations = CitationGenerator.generate(sanitized_items)

        # 7. Determine AI Provider
        active_provider = self.ai_provider or get_ai_provider(provider_name)

        # Check Local Only Mode (Mock provider is always allowed as a local test provider)
        is_mock = (active_provider and active_provider.name == "mock") or (provider_name == "mock")
        is_local_only = getattr(settings, "local_only_mode", True) and not is_mock
        if provider_name in ("mock", "gemini"):
            is_local_only = False

        if is_local_only or not active_provider or not active_provider.is_available:
            # Local-Only Mode Response (without generative LLM)
            preview_snippets = "\n".join(
                [f"• {c.relative_path} ({c.location}): {c.snippet_preview}" for c in citations[:4]]
            )
            local_answer = (
                "Cloud generation is disabled (Local Only mode). "
                f"However, here are the most relevant evidence sources found in '{project['name']}':\n\n"
                f"{preview_snippets}"
            )
            return RAGResponse(
                answer=local_answer,
                provider="local",
                mode=search_mode.value,
                sources=citations,
                context_count=len(sanitized_items),
                redactions=total_redactions,
            )

        # 8. Build Grounded Prompts
        formatted_context = self.assembler.format_context_for_prompt(sanitized_items)
        system_prompt = self.prompt_builder.build_system_prompt(project_name=project.get("name"))
        user_prompt = self.prompt_builder.build_user_prompt(
            question=sanitized_question,
            formatted_context=formatted_context,
        )

        # 9. AI Generation
        try:
            gen_result = active_provider.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                context=formatted_context,
            )
            answer_text = gen_result.text
            provider_label = active_provider.name
        except Exception as err:
            logger.error(f"Error during AI generation with {active_provider.name}: {err}")
            answer_text = f"An error occurred while generating the answer with {active_provider.name}: {err}"
            provider_label = f"{active_provider.name} (failed)"

        return RAGResponse(
            answer=answer_text,
            provider=provider_label,
            mode=search_mode.value,
            sources=citations,
            context_count=len(sanitized_items),
            redactions=total_redactions,
        )
