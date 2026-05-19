"""Shared service singletons for all agent nodes.

Every heavy service (retrieval, assembler, verifier, user-doc retrieval)
is instantiated **exactly once** here and imported by all nodes.  This
avoids the problem of each node file creating its own instance and
loading the cross-encoder / embedding models multiple times at startup.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from app.services.retrieval_service import RetrievalService
from app.services.context_assembler import MultiSourceContextAssembler
from app.services.citation_verifier import CitationVerifier
from app.services.user_document_retrieval_service import UserDocumentRetrievalService

logger = logging.getLogger(__name__)

# ── Eagerly loaded singletons (used by every request) ──

retrieval_service = RetrievalService()
context_assembler = MultiSourceContextAssembler()
citation_verifier = CitationVerifier()


# ── Lazily loaded singleton (only when user documents are involved) ──

@lru_cache(maxsize=1)
def get_user_doc_retrieval() -> UserDocumentRetrievalService:
    """Initialise the user-document retrieval service on first use."""
    logger.info("Initialising UserDocumentRetrievalService (lazy, one-time).")
    return UserDocumentRetrievalService()
