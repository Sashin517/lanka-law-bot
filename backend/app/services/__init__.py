"""Lazy compatibility exports for the services package.

Importing a lightweight submodule must not initialize retrievers, download ML
models, or construct the agent graph. Existing ``from app.services import X``
callers remain supported through PEP 562 lazy attribute resolution.
"""

from __future__ import annotations

from importlib import import_module

_EXPORTS = {
    "RetrievalService": "app.services.retrieval.retrieval_service",
    "get_retrieval_service": "app.services.retrieval.retrieval_service",
    "UserDocumentRetrievalService": "app.services.retrieval.user_document_retrieval_service",
    "UserDocumentVectorStore": "app.services.retrieval.user_document_vector_store",
    "LegalVectorStore": "app.services.retrieval.legal_vector_store",
    "PineconeLegalRetriever": "app.services.retrieval.legal_vector_store",
    "VoyageEmbeddingService": "app.services.retrieval.voyage_embedding_service",
    "reciprocal_rank_fusion": "app.services.retrieval.retrieval_fusion",
    "retrieval_dedup_key": "app.services.retrieval.retrieval_fusion",
    "DocumentParser": "app.services.ingestion.document_parser",
    "ParsedDocument": "app.services.ingestion.document_parser",
    "DocumentStorage": "app.services.ingestion.document_storage",
    "StoredFile": "app.services.ingestion.document_storage",
    "LegalDocumentChunker": "app.services.ingestion.legal_chunker",
    "ChunkingDocumentContext": "app.services.ingestion.legal_chunker",
    "LegalChunk": "app.services.ingestion.legal_chunker",
    "ChunkSet": "app.services.ingestion.legal_chunker",
    "IngestionJobService": "app.services.ingestion.ingestion_jobs",
    "GenerationService": "app.services.generation.generation_service",
    "ContextAssembler": "app.services.generation.context_assembler",
    "MultiSourceContextAssembler": "app.services.generation.context_assembler",
    "CitationVerifier": "app.services.generation.citation_verifier",
    "ConversationService": "app.services.conversation_service",
    "MemoryService": "app.services.memory_service",
}

__all__ = list(_EXPORTS)


def __getattr__(name: str):
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(name)
    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value
