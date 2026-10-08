"""
Complete RAG Pipeline orchestrator for SVANT Phase 3.
Coordinates retrieval, deduplication, local secret redaction, grounded prompt creation,
AI generation (Gemini, Mock, or Local-Only), and citation generation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import uuid
from svant.config import settings
from svant.core.ai.base import AIProvider
from svant.core.ai.factory import get_ai_provider
from svant.core.assistant import ProjectAssistant
from svant.core.privacy.redactor import SecretRedactor
from svant.core.rag.citations import Citation, CitationGenerator
from svant.core.rag.context import ContextAssembler, ContextItem
from svant.core.rag.prompt import GroundedPromptBuilder
from svant.core.rag.smart_selector import SmartContextSelector
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
    conversation_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "answer": self.answer,
            "provider": self.provider,
            "mode": self.mode,
            "sources": [s.to_dict() for s in self.sources],
            "context_count": self.context_count,
            "redactions": self.redactions,
            "conversation_id": self.conversation_id,
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
        smart_selector: Optional[SmartContextSelector] = None,
        assistant: Optional[ProjectAssistant] = None,
    ) -> None:
        self.repo = repo
        self.search_service = search_service or SearchService(repo)
        self.ai_provider = ai_provider
        self.redactor = redactor or SecretRedactor()
        self.assembler = assembler or ContextAssembler()
        self.prompt_builder = prompt_builder or GroundedPromptBuilder()
        self.smart_selector = smart_selector or SmartContextSelector(
            repo=self.repo,
            search_service=self.search_service,
            assembler=self.assembler,
        )
        self.assistant = assistant or ProjectAssistant(repo=self.repo, redactor=self.redactor)
        self._sessions: Dict[str, List[Dict[str, str]]] = {}

    def _resolve_follow_up_finding(
        self,
        project_id: str,
        message: str,
        history: Optional[List[Dict[str, str]]],
    ) -> Optional[Dict[str, Any]]:
        """Resolve references like 'the second one', 'number 1', 'why', or 'that finding' to a specific finding."""
        q = message.lower().strip()
        open_findings = self.repo.list_findings(project_id, status="open")
        if not open_findings:
            return None

        # Exclude general priority questions
        if any(w in q for w in ("fix first", "what to fix", "what should i fix", "what should we fix")):
            return None

        # 1. Ordinal matching
        idx_match = None
        if any(w in q for w in ("the first one", "first one", "1st one", "number 1", "#1", "first finding", "first issue")):
            idx_match = 0
        elif any(w in q for w in ("the second one", "second one", "second", "2nd", "number 2", "#2", "second finding", "second issue")):
            idx_match = 1
        elif any(w in q for w in ("the third one", "third one", "third", "3rd", "number 3", "#3", "third finding", "third issue")):
            idx_match = 2
        elif any(w in q for w in ("the fourth one", "fourth one", "fourth", "4th", "number 4", "#4", "fourth finding", "fourth issue")):
            idx_match = 3
        elif any(w in q for w in ("the fifth one", "fifth one", "fifth", "5th", "number 5", "#5", "fifth finding", "fifth issue")):
            idx_match = 4

        if idx_match is not None and 0 <= idx_match < len(open_findings):
            return open_findings[idx_match]

        # 2. Check direct mention of finding title or filename
        for f in open_findings:
            f_title = f.get("title", "").lower()
            f_rel = (f.get("relative_path") or "").lower()
            f_name = Path(f_rel).name.lower() if f_rel else ""
            if (f_title and f_title in q) or (f_name and len(f_name) > 3 and f_name in q):
                return f

        # 3. Conversational follow-ups (e.g. "why", "tell me more", "how do i fix", "that finding")
        is_follow_up = any(w in q for w in ("why", "why?", "tell me more", "how do i fix", "how to fix", "how can i fix", "elaborate", "that finding", "that issue", "that problem"))
        if is_follow_up and history:
            # Check if recent history explicitly referenced a finding
            hist_text = " ".join([h.get("content", "").lower() for h in history[-3:]])
            for f in open_findings:
                if f.get("title", "").lower() in hist_text or (f.get("relative_path") and f["relative_path"].lower() in hist_text):
                    return f
            # Default to top priority open finding
            return open_findings[0]

        return None

    def query(
        self,
        project_id: str,
        message: str,
        search_mode: SearchMode = SearchMode.HYBRID,
        top_k: Optional[int] = None,
        provider_name: Optional[str] = None,
        conversation_id: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> RAGResponse:
        """
        Execute grounded RAG workflow for a user question with intent-aware context selection.
        """
        clean_msg = message.strip()
        conv_id = conversation_id or str(uuid.uuid4())

        # Load session history if exists
        active_history = list(history) if history is not None else list(self._sessions.get(conv_id, []))

        if not clean_msg:
            return RAGResponse(
                answer="Please enter a question about your project.",
                provider="none",
                mode=search_mode.value,
                sources=[],
                context_count=0,
                redactions=0,
                conversation_id=conv_id,
            )

        # 1. Validate project
        project = self.repo.get_project(project_id)
        if not project:
            raise ValueError(f"Project '{project_id}' not found.")

        # 2. Local Privacy & Redaction on user question
        user_q_redact = self.redactor.redact(clean_msg)
        sanitized_question = user_q_redact.sanitized_text
        total_redactions = user_q_redact.redaction_count

        # 3. Resolve follow-up references
        ref_finding = self._resolve_follow_up_finding(project_id, clean_msg, active_history)

        # 4. Smart Context Assembly (Intent-driven + hybrid search chunks)
        fetch_k = top_k or self.assembler.top_k
        raw_items = self.smart_selector.build_context(
            project_id=project_id,
            query=clean_msg,
            search_mode=search_mode,
            top_k=fetch_k,
            referenced_finding=ref_finding,
            history=active_history,
        )

        # Determine AI Provider & Mode
        active_provider = self.ai_provider or get_ai_provider(provider_name)
        is_mock = (active_provider and active_provider.name == "mock") or (provider_name == "mock")
        is_local_only = getattr(settings, "local_only_mode", True) and not is_mock
        if provider_name in ("mock", "gemini"):
            is_local_only = False

        # Handle Empty Retrieval for cloud/generative providers
        if not raw_items and not is_local_only:
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
                conversation_id=conv_id,
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
                category=getattr(itm, "category", "RELEVANT_SOURCE_CHUNKS"),
                metadata=getattr(itm, "metadata", None),
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
            # Synthesize intelligent, grounded, question-specific response
            intents = self.smart_selector.classify_intent(clean_msg, history=active_history)
            local_answer = self.assistant.answer_question(
                project_id=project_id,
                question=sanitized_question,
                intents=intents,
                context_items=sanitized_items,
                citations=citations,
                referenced_finding=ref_finding,
                history=active_history,
            )
            # Record exchange in conversation session
            sess = self._sessions.setdefault(conv_id, [])
            sess.append({"role": "user", "content": clean_msg})
            sess.append({"role": "assistant", "content": local_answer})

            return RAGResponse(
                answer=local_answer,
                provider="local",
                mode=search_mode.value,
                sources=citations,
                context_count=len(sanitized_items),
                redactions=total_redactions,
                conversation_id=conv_id,
            )

        # 8. Build Grounded Prompts
        formatted_context = self.assembler.format_context_for_prompt(sanitized_items)
        system_prompt = self.prompt_builder.build_system_prompt(project_name=project.get("name"))
        user_prompt = self.prompt_builder.build_user_prompt(
            question=sanitized_question,
            formatted_context=formatted_context,
            conversation_history=active_history,
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

        # Record exchange in conversation session
        sess = self._sessions.setdefault(conv_id, [])
        sess.append({"role": "user", "content": clean_msg})
        sess.append({"role": "assistant", "content": answer_text})

        return RAGResponse(
            answer=answer_text,
            provider=provider_label,
            mode=search_mode.value,
            sources=citations,
            context_count=len(sanitized_items),
            redactions=total_redactions,
            conversation_id=conv_id,
        )
