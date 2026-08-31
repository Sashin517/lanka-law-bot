from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import ConfigDict

from app.core.config import settings
from app.services.retrieval.retrieval_fusion import reciprocal_rank_fusion

logger = logging.getLogger(__name__)


RETURN_FIELDS = [
    "title",
    "citation",
    "section_label",
    "body",
    "text",
    "chunk_id",
    "parent_id",
    "chunk_type",
    "section",
    "section_number",
    "breadcrumb",
    "page_start",
    "page_end",
    "source_filename",
    "source_type",
    "doc_type",
    "source_uri",
    "source_sha256",
    "authoritative",
    "work_id",
    "expression_id",
    "case_name",
    "court",
    "docket_number",
    "reporter_citation",
    "work_year",
    "year",
    "chapter_number",
    "valid_from",
    "valid_to",
    "is_current",
    "corpus_version",
    "schema_version",
    "text_hash",
]


class LegalVectorStore:
    """Pinecone legal document vector store supporting dense vector search and BM25 document search."""

    def __init__(self) -> None:
        if not settings.PINECONE_API_KEY:
            raise RuntimeError("PINECONE_API_KEY is required for legal retrieval.")
        if settings.JINA_EMBEDDING_DIMENSION != settings.PINECONE_EMBEDDING_DIMENSION:
            raise RuntimeError(
                "JINA_EMBEDDING_DIMENSION and PINECONE_EMBEDDING_DIMENSION must match."
            )
        try:
            from pinecone import Pinecone
        except ImportError as exc:
            raise RuntimeError(
                "pinecone is not installed. Install backend requirements."
            ) from exc

        self._pc = Pinecone(api_key=settings.PINECONE_API_KEY)

        # Dense vector index configuration
        self.dense_index_name = getattr(settings, "PINECONE_LEGAL_INDEX_NAME", "lawdex-legal-index")
        self.dense_namespace = getattr(settings, "PINECONE_LEGAL_NAMESPACE", "legal_corpus")
        if settings.PINECONE_LEGAL_INDEX_HOST:
            self._dense_index = self._pc.Index(host=settings.PINECONE_LEGAL_INDEX_HOST)
        else:
            self._dense_index = self._pc.Index(self.dense_index_name)

        # BM25 document index configuration
        self.bm25_index_name = getattr(settings, "PINECONE_LEGAL_BM25_INDEX_NAME", "lawdex-legal-bm25-index")
        self.bm25_namespace = getattr(settings, "PINECONE_LEGAL_BM25_NAMESPACE", "legal_corpus")
        bm25_host = getattr(settings, "PINECONE_LEGAL_BM25_INDEX_HOST", "")
        if bm25_host:
            self._bm25_index = self._pc.preview.index(host=bm25_host)
        else:
            self._bm25_index = self._pc.preview.index(name=self.bm25_index_name)

        self.collection = self.dense_index_name
        self.namespace = self.dense_namespace

    def ensure_collection(self) -> None:
        """Validate readiness of Pinecone indices."""
        try:
            dense_desc = self._pc.describe_index(self.dense_index_name)
            dense_ready = getattr(dense_desc.status, "ready", False) if not isinstance(dense_desc.status, dict) else dense_desc.status.get("ready", False)
            if not dense_ready:
                logger.warning("Dense vector index '%s' is not ready yet.", self.dense_index_name)
        except Exception as exc:
            logger.warning("Could not describe dense index '%s': %s", self.dense_index_name, exc)

    @staticmethod
    def _child_filter(metadata_filters: dict | None) -> dict:
        required = {"chunk_type": {"$eq": "child"}}
        if not metadata_filters:
            return required
        return {"$and": [required, metadata_filters]}

    @staticmethod
    def _dense_match_to_langchain(match: Any, *, channel: str) -> Document:
        metadata = dict(getattr(match, "metadata", {}) or {})
        point_id = getattr(match, "id", "")
        score = getattr(match, "score", None)
        body = metadata.get("text") or metadata.get("body") or ""
        metadata["point_id"] = point_id
        metadata["retrieval_channel"] = channel
        if score is not None:
            metadata["retrieval_score"] = float(score)
        return Document(page_content=body, metadata=metadata)

    @staticmethod
    def _preview_document_to_langchain(
        match: Any,
        *,
        channel: str,
    ) -> Document:
        fields = (
            dict(match.to_dict())
            if hasattr(match, "to_dict")
            else dict(getattr(match, "_data", {}))
        )
        point_id = fields.pop("_id", getattr(match, "id", ""))
        score = fields.pop("_score", getattr(match, "score", None))
        body = fields.get("text") or fields.get("body") or ""
        fields["point_id"] = point_id
        fields["retrieval_channel"] = channel
        if score is not None:
            fields["retrieval_score"] = float(score)
        return Document(page_content=body, metadata=fields)

    def search_children(
        self,
        query: str,
        limit: int = 5,
        metadata_filters: dict | None = None,
    ) -> list[Document]:
        """Rank child documents by dense vector similarity."""
        from app.services.retrieval.jina_embedding_service import (
            get_jina_embedding_service,
        )

        query_vector = get_jina_embedding_service().embed_query(query)
        filter_dict = self._child_filter(metadata_filters)

        results = self._dense_index.query(
            vector=query_vector,
            top_k=limit,
            namespace=self.dense_namespace,
            include_metadata=True,
            filter=filter_dict,
        )
        return [
            self._dense_match_to_langchain(match, channel="dense")
            for match in results.matches
        ]

    def search_children_bm25(
        self,
        query: str,
        limit: int = 5,
        metadata_filters: dict | None = None,
    ) -> list[Document]:
        """Rank child documents using Pinecone BM25 document search."""
        try:
            results = self._bm25_index.documents.search(
                namespace=self.bm25_namespace,
                top_k=limit,
                score_by=[
                    {
                        "type": "text",
                        "field": "text",
                        "query": query,
                    },
                ],
                include_fields=RETURN_FIELDS,
                filter=self._child_filter(metadata_filters),
            )
            return [
                self._preview_document_to_langchain(match, channel="bm25")
                for match in results.matches
            ]
        except Exception as exc:
            logger.warning("BM25 document search failed, falling back to empty list: %s", exc)
            return []

    def fetch_parents_batch(self, parent_ids: list[str]) -> dict[str, Document]:
        """Batch fetch multiple parent documents in a single Pinecone network call.
        
        Fetches up to 100 IDs per network call without in-memory caching.
        """
        if not parent_ids:
            return {}

        unique_ids = list(dict.fromkeys(pid for pid in parent_ids if pid))
        if not unique_ids:
            return {}

        results: dict[str, Document] = {}
        missing_ids = list(unique_ids)

        # Attempt 1: Batch fetch from dense vector index
        try:
            # Pinecone fetch supports batches of IDs (standard batch size <= 100)
            for i in range(0, len(missing_ids), 100):
                batch_ids = missing_ids[i : i + 100]
                response = self._dense_index.fetch(
                    ids=batch_ids,
                    namespace=self.dense_namespace,
                )
                vectors = getattr(response, "vectors", {}) or {}
                for pid, vec in vectors.items():
                    metadata = dict(getattr(vec, "metadata", {}) or {})
                    body = metadata.get("text") or metadata.get("body") or ""
                    metadata["point_id"] = pid
                    metadata["retrieval_channel"] = "parent_fetch"
                    if metadata.get("chunk_type") and metadata.get("chunk_type") != "parent":
                        logger.warning("ID %s resolved to a non-parent document in dense index", pid)
                    results[pid] = Document(page_content=body, metadata=metadata)
        except Exception as exc:
            logger.debug("Batch fetch parents from dense index failed: %s", exc)

        # Attempt 2: Fetch any missing IDs from BM25 document index
        remaining_ids = [pid for pid in unique_ids if pid not in results]
        if remaining_ids:
            try:
                for i in range(0, len(remaining_ids), 100):
                    batch_ids = remaining_ids[i : i + 100]
                    response = self._bm25_index.documents.fetch(
                        namespace=self.bm25_namespace,
                        ids=batch_ids,
                        include_fields=RETURN_FIELDS,
                    )
                    docs = getattr(response, "documents", {}) or {}
                    for pid, parent in docs.items():
                        if parent is not None:
                            results[pid] = self._preview_document_to_langchain(
                                parent, channel="parent_fetch"
                            )
            except Exception as exc:
                logger.debug("Batch fetch parents from BM25 index failed: %s", exc)

        return results

    def fetch_parent(self, parent_id: str) -> Document | None:
        """Fetch an exact parent document by ID from dense index or BM25 index."""
        if not parent_id:
            return None
        batch_res = self.fetch_parents_batch([parent_id])
        return batch_res.get(parent_id)


class PineconeLegalRetriever(BaseRetriever):
    """LangChain wrapper around dense document search."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    store: LegalVectorStore
    k: int = 5
    metadata_filters: dict | None = None

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        return self.store.search_children(
            query=query, limit=self.k, metadata_filters=self.metadata_filters
        )


class PineconeLegalBM25Retriever(BaseRetriever):
    """LangChain wrapper around multi-field BM25 document search."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    store: LegalVectorStore
    k: int = 5
    metadata_filters: dict | None = None

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        return self.store.search_children_bm25(
            query=query, limit=self.k, metadata_filters=self.metadata_filters
        )


class PineconeLegalHybridRetriever(BaseRetriever):
    """Run dense and BM25 searches concurrently and fuse by shared chunk ID."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    store: LegalVectorStore
    k: int = 5
    dense_weight: float = 0.6
    sparse_weight: float = 0.4
    metadata_filters: dict | None = None

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="legal-search") as pool:
            dense_future = pool.submit(
                self.store.search_children,
                query,
                self.k,
                self.metadata_filters,
            )
            bm25_future = pool.submit(
                self.store.search_children_bm25,
                query,
                self.k,
                self.metadata_filters,
            )
            dense_error = sparse_error = None
            try:
                dense = dense_future.result()
            except Exception as exc:
                dense_error = exc
                dense = []
                logger.exception("Dense Pinecone search failed")
            try:
                sparse = bm25_future.result()
            except Exception as exc:
                sparse_error = exc
                sparse = []
                logger.exception("BM25 Pinecone search failed")

        if dense_error and sparse_error:
            raise RuntimeError("Both Pinecone retrieval channels failed") from dense_error
        return reciprocal_rank_fusion(
            [dense, sparse],
            weights=[self.dense_weight, self.sparse_weight],
        )
