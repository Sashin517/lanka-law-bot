"""
LangChain retriever wrappers for Neo4j.
Allows Neo4j vector and full-text searches to be integrated into LangChain's EnsembleRetriever
and other abstraction layers.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

from app.core.config import settings
from app.services.retrieval.neo4j_graph_store import Neo4jGraphStore
from app.services.retrieval.gemini_embedding_service import get_gemini_embedding_service

logger = logging.getLogger(__name__)


class Neo4jVectorRetriever(BaseRetriever):
    """LangChain BaseRetriever wrapper for Neo4j dense semantic search."""

    store: Any  # Neo4jGraphStore
    k: int = 30
    year_filter: Optional[int] = None
    source_type_filter: Optional[str] = None

    class Config:
        arbitrary_types_allowed = True

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> List[Document]:
        """Embeds the query text using Gemini Embedding API and performs vector search in Neo4j."""
        embed_service = get_gemini_embedding_service()
        query_embedding = embed_service.embed_query(query)
        return self.store.vector_search(
            query_embedding=query_embedding,
            top_k=self.k,
            year_filter=self.year_filter,
            source_type_filter=self.source_type_filter,
        )



class Neo4jFulltextRetriever(BaseRetriever):
    """LangChain BaseRetriever wrapper for Neo4j Lucene lexical search."""

    store: Any  # Neo4jGraphStore
    k: int = 30
    year_filter: Optional[int] = None

    class Config:
        arbitrary_types_allowed = True

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> List[Document]:
        """Runs lexical search directly on the Neo4j full-text index."""
        return self.store.fulltext_search(
            query_text=query,
            top_k=self.k,
            year_filter=self.year_filter,
        )
