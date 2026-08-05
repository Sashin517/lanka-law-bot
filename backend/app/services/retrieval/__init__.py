"""Lazy exports for retrieval services; imports have no model/network effects."""
from __future__ import annotations

from importlib import import_module


_EXPORTS = {
    "RetrievalService": "app.services.retrieval.retrieval_service",
    "get_retrieval_service": "app.services.retrieval.retrieval_service",
    "UserDocumentRetrievalService": "app.services.retrieval.user_document_retrieval_service",
    "UserDocumentVectorStore": "app.services.retrieval.user_document_vector_store",
    "LegalVectorStore": "app.services.retrieval.legal_vector_store",
    "PineconeLegalBM25Retriever": "app.services.retrieval.legal_vector_store",
    "PineconeLegalRetriever": "app.services.retrieval.legal_vector_store",
    "VoyageEmbeddingService": "app.services.retrieval.voyage_embedding_service",
    "JinaEmbeddingService": "app.services.retrieval.jina_embedding_service",
    "get_jina_embedding_service": "app.services.retrieval.jina_embedding_service",
    "reciprocal_rank_fusion": "app.services.retrieval.retrieval_fusion",
    "retrieval_dedup_key": "app.services.retrieval.retrieval_fusion",
    "Neo4jGraphStore": "app.services.retrieval.neo4j_graph_store",
    "Neo4jVectorRetriever": "app.services.retrieval.neo4j_retrievers",
    "Neo4jFulltextRetriever": "app.services.retrieval.neo4j_retrievers",
    "Neo4jRetrievalService": "app.services.retrieval.neo4j_retrieval_service",
    "get_neo4j_retrieval_service": "app.services.retrieval.neo4j_retrieval_service",
}

__all__ = list(_EXPORTS)


def __getattr__(name: str):
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(name)
    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value
