"""
Retrieval-Augmented Generation (RAG) package for SVANT.
"""

from svant.core.rag.citations import Citation, CitationGenerator
from svant.core.rag.context import ContextAssembler, ContextItem
from svant.core.rag.pipeline import RAGPipeline, RAGResponse
from svant.core.rag.prompt import GroundedPromptBuilder

__all__ = [
    "ContextItem",
    "ContextAssembler",
    "Citation",
    "CitationGenerator",
    "GroundedPromptBuilder",
    "RAGPipeline",
    "RAGResponse",
]
