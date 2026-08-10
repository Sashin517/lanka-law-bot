"""Shared service singletons for all agent nodes.

Every heavy service (retrieval, assembler, verifier, user-doc retrieval)
is instantiated **exactly once** here and imported by all nodes.  This
avoids the problem of each node file creating its own instance and
loading the cross-encoder / embedding models multiple times at startup.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from app.core.config import settings
from app.services.retrieval.retrieval_service import RetrievalService
from app.services.retrieval.neo4j_retrieval_service import get_neo4j_retrieval_service
from app.services.generation.context_assembler import MultiSourceContextAssembler
from app.services.generation.citation_verifier import CitationVerifier
from app.services.retrieval.user_document_retrieval_service import (
    UserDocumentRetrievalService,
)

logger = logging.getLogger(__name__)


# Helper to get the configured legal retrieval service
def get_configured_retrieval_service():
    backend = getattr(settings, "RETRIEVAL_BACKEND", "pinecone").lower()
    if backend == "neo4j":
        logger.info("Routing shared agent legal retrieval to NEO4J GraphRAG backend.")
        return get_neo4j_retrieval_service()
    else:
        logger.info("Routing shared agent legal retrieval to PINECONE backend.")
        return RetrievalService()


# ── Eagerly loaded singletons (used by every request) ──

retrieval_service = get_configured_retrieval_service()
context_assembler = MultiSourceContextAssembler()
citation_verifier = CitationVerifier()


# ── Lazily loaded singleton (only when user documents are involved) ──


@lru_cache(maxsize=1)
def get_user_doc_retrieval() -> UserDocumentRetrievalService:
    """Initialise the user-document retrieval service on first use."""
    logger.info("Initialising UserDocumentRetrievalService (lazy, one-time).")
    return UserDocumentRetrievalService()
