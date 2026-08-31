from __future__ import annotations

import logging

from langchain_community.cross_encoders import HuggingFaceCrossEncoder
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from langchain_classic.retrievers.document_compressors.cross_encoder_rerank import (
    CrossEncoderReranker,
)

from app.core.config import settings
from app.services.retrieval.cross_encoder_singleton import get_shared_cross_encoder
from app.services.retrieval.retrieval_fusion import reciprocal_rank_fusion, retrieval_dedup_key
from app.services.retrieval.user_document_vector_store import UserDocumentVectorStore

logger = logging.getLogger(__name__)


class UserDocumentRetrievalService:
    """
    Hybrid retrieval for uploaded user documents:

    1. Dense search in Pinecone over child chunks
    2. Sparse BM25 search over selected document child chunks
    3. Reciprocal Rank Fusion
    4. Cross-encoder reranking
    5. Parent chunk expansion from Pinecone
    """

    def __init__(self) -> None:
        self._vector_store = UserDocumentVectorStore()
        # In-memory cache for BM25Retriever keyed by (tenant_id, tuple of sorted document_ids)
        self._bm25_cache: dict[tuple[str, tuple[str, ...]], BM25Retriever] = {}
        self._reranker = CrossEncoderReranker(
            model=get_shared_cross_encoder(),
            top_n=settings.USER_DOC_RERANKER_TOP_N,
        )

    def search(
        self,
        query: str,
        document_ids: list[str],
        tenant_id: str = "local",
        user_id: str = "local_user",
        matter_id: str | None = None,
        top_k: int = 6,
        expand_parents: bool = True,
    ) -> list[dict]:
        document_ids = [doc_id for doc_id in dict.fromkeys(document_ids) if doc_id]
        if not document_ids:
            return []

        dense_docs = self._dense_search(
            query=query,
            document_ids=document_ids,
            tenant_id=tenant_id,
            user_id=user_id,
            matter_id=matter_id,
        )
        sparse_docs = self._sparse_search(
            query=query,
            document_ids=document_ids,
            tenant_id=tenant_id,
            user_id=user_id,
            matter_id=matter_id,
        )
        fused = reciprocal_rank_fusion([dense_docs, sparse_docs])
        reranked = self._rerank(query, fused)
        unique = self._deduplicate(reranked)

        results: list[dict] = []
        candidate_children = unique[:top_k]
        parent_map: dict[str, Document] = {}

        if expand_parents:
            needed_pids = [
                child.metadata.get("parent_id")
                for child in candidate_children
                if child.metadata.get("parent_id")
            ]
            if needed_pids:
                parent_map = self._vector_store.fetch_parents_batch(
                    parent_ids=needed_pids,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    document_ids=document_ids,
                )

        for child in candidate_children:
            parent = None
            if expand_parents:
                parent_id = child.metadata.get("parent_id")
                if parent_id:
                    parent = parent_map.get(parent_id)

            results.append(
                {
                    "child": child,
                    "parent": parent,
                    "metadata": child.metadata,
                    "source_family": "user_document",
                }
            )

        logger.info(
            "Retrieved %d user-document results for query='%s' docs=%d",
            len(results),
            query[:80],
            len(document_ids),
        )
        return results

    def _dense_search(
        self,
        query: str,
        document_ids: list[str],
        tenant_id: str,
        user_id: str,
        matter_id: str | None,
    ) -> list[Document]:
        try:
            return self._vector_store.search_children(
                query=query,
                document_ids=document_ids,
                tenant_id=tenant_id,
                user_id=user_id,
                matter_id=matter_id,
                limit=max(settings.RETRIEVAL_CANDIDATES_K, settings.USER_DOC_RERANKER_TOP_N * 3),
            )
        except Exception:
            logger.exception("User-document dense retrieval failed.")
            return []

    def _sparse_search(
        self,
        query: str,
        document_ids: list[str],
        tenant_id: str,
        user_id: str,
        matter_id: str | None,
    ) -> list[Document]:
        try:
            cache_key = (tenant_id, tuple(sorted(document_ids)))
            retriever = self._bm25_cache.get(cache_key)
            if retriever is None:
                child_docs = self._vector_store.load_child_documents_for_bm25(
                    document_ids=document_ids,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    matter_id=matter_id,
                )
                if not child_docs:
                    return []
                retriever = BM25Retriever.from_documents(
                    child_docs,
                    k=max(settings.RETRIEVAL_CANDIDATES_K, settings.USER_DOC_RERANKER_TOP_N * 3),
                )
                self._bm25_cache[cache_key] = retriever
            return retriever.invoke(query)
        except Exception:
            logger.exception("User-document sparse retrieval failed.")
            return []

    def _rerank(self, query: str, documents: list[Document]) -> list[Document]:
        if not documents:
            return []
        try:
            return list(self._reranker.compress_documents(documents, query))
        except Exception:
            logger.exception("User-document reranking failed; using fused order.")
            return documents[: settings.USER_DOC_RERANKER_TOP_N]

    @staticmethod
    def _deduplicate(documents: list[Document]) -> list[Document]:
        seen: set[str] = set()
        unique: list[Document] = []
        for document in documents:
            key = retrieval_dedup_key(document)
            if key in seen:
                continue
            seen.add(key)
            unique.append(document)
        return unique
