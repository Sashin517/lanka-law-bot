"""Shared service accessors for all agent nodes.

Retrieval clients and models are intentionally constructed on first use.  Importing
the agent graph must stay cheap and must not pull optional native dependencies into
the chat worker before a request actually needs them.
"""

from __future__ import annotations

import logging
from threading import Lock
from typing import TYPE_CHECKING, Any

from app.core.config import settings
from app.services.generation.citation_verifier import CitationVerifier
from app.services.generation.context_assembler import MultiSourceContextAssembler

if TYPE_CHECKING:
    from app.services.retrieval.user_document_retrieval_service import (
        UserDocumentRetrievalService,
    )

logger = logging.getLogger(__name__)


_retrieval_service: Any | None = None
_retrieval_lock = Lock()
_user_doc_retrieval: UserDocumentRetrievalService | None = None
_user_doc_lock = Lock()


def _build_retrieval_service() -> Any:
    """Construct only the configured legal retrieval backend."""

    backend = getattr(settings, "RETRIEVAL_BACKEND", "pinecone").lower()
    if backend == "neo4j":
        logger.info("Routing shared agent legal retrieval to NEO4J GraphRAG backend.")
        from app.services.retrieval.neo4j_retrieval_service import (
            get_neo4j_retrieval_service,
        )

        return get_neo4j_retrieval_service()

    logger.info("Routing shared agent legal retrieval to PINECONE backend.")
    from app.services.retrieval.retrieval_service import RetrievalService

    return RetrievalService()


def get_retrieval_service() -> Any:
    """Return the process-local retrieval singleton, constructing it once."""

    global _retrieval_service
    if _retrieval_service is None:
        with _retrieval_lock:
            if _retrieval_service is None:
                _retrieval_service = _build_retrieval_service()
    return _retrieval_service


def get_configured_retrieval_service() -> Any:
    """Backward-compatible name for the configured retrieval accessor."""

    return _build_retrieval_service()


class LazyRetrievalService:
    """Compatibility proxy used by existing nodes and tests."""

    def search(self, *args: Any, **kwargs: Any) -> Any:
        return get_retrieval_service().search(*args, **kwargs)


retrieval_service = LazyRetrievalService()
context_assembler = MultiSourceContextAssembler()
citation_verifier = CitationVerifier()


# ── Lazily loaded singleton (only when user documents are involved) ──


def get_user_doc_retrieval() -> UserDocumentRetrievalService:
    """Initialise the user-document retrieval service on first use."""

    global _user_doc_retrieval
    if _user_doc_retrieval is None:
        with _user_doc_lock:
            if _user_doc_retrieval is None:
                logger.info(
                    "Initialising UserDocumentRetrievalService (lazy, one-time)."
                )
                from app.services.retrieval.user_document_retrieval_service import (
                    UserDocumentRetrievalService,
                )

                _user_doc_retrieval = UserDocumentRetrievalService()
    return _user_doc_retrieval
