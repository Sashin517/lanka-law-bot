from __future__ import annotations

import logging

from langchain_community.cross_encoders import HuggingFaceCrossEncoder
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from langchain_classic.retrievers.document_compressors.cross_encoder_rerank import (
    CrossEncoderReranker,
)

from app.core.config import settings
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
        cross_encoder = HuggingFaceCrossEncoder(model_name=settings.RERANKER_MODEL)
        self._reranker = CrossEncoderReranker(
            model=cross_encoder,
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
        for child in unique[:top_k]:
            parent = None
            if expand_parents:
                parent_id = child.metadata.get("parent_id")
                document_id = child.metadata.get("document_id")
                if parent_id and document_id:
                    parent = self._vector_store.fetch_parent(
                        parent_id=parent_id,
                        tenant_id=tenant_id,
                        user_id=user_id,
                        document_id=document_id,
                    )

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
