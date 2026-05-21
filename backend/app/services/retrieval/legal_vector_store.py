import logging
from typing import Any

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

from app.core.config import settings

logger = logging.getLogger(__name__)


class LegalVectorStore:
    def __init__(self) -> None:
        if not settings.PINECONE_API_KEY:
            raise RuntimeError(
                "PINECONE_API_KEY is required for legal document ingestion."
            )
        if not settings.PINECONE_LEGAL_INDEX_HOST:
            raise RuntimeError(
                "PINECONE_LEGAL_INDEX_HOST is required for legal document ingestion."
            )
        try:
            from pinecone import Pinecone
        except ImportError as exc:
            raise RuntimeError(
                "pinecone is not installed. Install backend requirements."
            ) from exc

        self._pc = Pinecone(api_key=settings.PINECONE_API_KEY)
        self._index = self._pc.Index(host=settings.PINECONE_LEGAL_INDEX_HOST)
        self._bm25_index = (
            self._pc.preview.index(host=settings.PINECONE_LEGAL_BM25_INDEX_HOST)
            if settings.PINECONE_LEGAL_BM25_INDEX_HOST
            else None
        )
        self.collection = settings.PINECONE_LEGAL_INDEX_NAME
        self.namespace = settings.PINECONE_LEGAL_NAMESPACE
        self.bm25_collection = settings.PINECONE_LEGAL_BM25_INDEX_NAME
        self.bm25_namespace = settings.PINECONE_LEGAL_BM25_NAMESPACE

    def ensure_collection(self) -> None:
        """Verify the Pinecone index exists and is ready."""
        try:
            desc = self._pc.describe_index(self.collection)
            logger.info(
                "Pinecone index '%s' is ready (dimension=%s, metric=%s).",
                self.collection,
                getattr(desc, "dimension", "?"),
                getattr(desc, "metric", "?"),
            )
        except Exception as exc:
            raise RuntimeError(
                f"Cannot reach Pinecone index '{self.collection}': {exc}"
            ) from exc

    def _hit_to_document(self, hit: Any) -> Document:
        metadata = (
            dict(hit.fields or {})
            if hasattr(hit, "fields") and hit.fields
            else dict(hit.metadata or {})
        )
        text = metadata.pop("text", "") or ""
        metadata["point_id"] = hit.id
        return Document(page_content=text, metadata=metadata)

    @staticmethod
    def _bm25_match_to_document(match: Any) -> Document:
        metadata = (
            dict(match.to_dict())
            if hasattr(match, "to_dict")
            else dict(getattr(match, "_data", {}))
        )
        point_id = metadata.pop("_id", getattr(match, "id", ""))
        metadata.pop("_score", None)
        text = metadata.pop("text", "") or ""
        metadata["point_id"] = point_id
        return Document(page_content=text, metadata=metadata)

    def search_children(
        self,
        query: str,
        limit: int = 5,
        metadata_filters: dict | None = None,
    ) -> list[Document]:
        """Dense semantic search via Pinecone search_records."""
        filter_dict = {"chunk_type": {"$eq": "child"}}
        if metadata_filters:
            filter_dict.update(metadata_filters)

        results = self._index.search_records(
            namespace=self.namespace,
            inputs={"text": query},
            top_k=limit,
            filter=filter_dict,
        )
        return [
            self._hit_to_document(hit)
            for hit in (results.result.hits if results.result else [])
        ]

    def search_children_bm25(
        self,
        query: str,
        limit: int = 5,
        metadata_filters: dict | None = None,
    ) -> list[Document]:
        """BM25 full-text search via Pinecone document search."""
        if self._bm25_index is None:
            raise RuntimeError(
                "PINECONE_LEGAL_BM25_INDEX_HOST is required for Pinecone BM25 search."
            )

        filter_dict = {"chunk_type": {"$eq": "child"}}
        if metadata_filters:
            filter_dict.update(metadata_filters)

        results = self._bm25_index.documents.search(
            namespace=self.bm25_namespace,
            top_k=limit,
            score_by=[{"type": "text", "field": "text", "query": query}],
            include_fields=["*"],
            filter=filter_dict,
        )
        return [self._bm25_match_to_document(match) for match in results.matches]

    def load_children_for_bm25(self, limit: int = 50000) -> list[Document]:
        """Load child chunk documents for BM25 sparse search using fetch_by_metadata."""
        meta_filter = {"chunk_type": {"$eq": "child"}}
        documents: list[Document] = []
        pagination_token: str | None = None

        while len(documents) < limit:
            batch_limit = min(1000, limit - len(documents))
            kwargs: dict = {
                "namespace": self.namespace,
                "filter": meta_filter,
                "limit": batch_limit,
            }
            if pagination_token:
                kwargs["pagination_token"] = pagination_token

            response = self._index.fetch_by_metadata(**kwargs)

            for record in (response.vectors or {}).values():
                metadata = dict(record.metadata or {})
                text = metadata.pop("text", "") or ""
                metadata["point_id"] = record.id
                documents.append(Document(page_content=text, metadata=metadata))

            pagination_token = (
                response.pagination.get("next") if response.pagination else None
            )
            if not pagination_token:
                break

        return documents[:limit]

    def fetch_parent(self, parent_id: str) -> Document | None:
        """Fetch parent chunk by chunk_id using a dummy dense search with exact metadata filter."""
        query_filter = {
            "chunk_type": {"$eq": "parent"},
            "chunk_id": {"$eq": parent_id},
        }
        results = self._index.search_records(
            namespace=self.namespace,
            inputs={"text": "dummy query to fetch parent by id"},
            top_k=1,
            filter=query_filter,
        )
        hits = results.result.hits if results.result else []
        return self._hit_to_document(hits[0]) if hits else None


class PineconeLegalRetriever(BaseRetriever):
    """LangChain BaseRetriever wrapper around LegalVectorStore dense search."""

    store: LegalVectorStore
    k: int = 5
    metadata_filters: dict | None = None

    class Config:
        arbitrary_types_allowed = True

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        """Execute the dense search on Pinecone."""
        return self.store.search_children(
            query=query, limit=self.k, metadata_filters=self.metadata_filters
        )


class PineconeLegalBM25Retriever(BaseRetriever):
    """LangChain BaseRetriever wrapper around Pinecone BM25 FTS search."""

    store: LegalVectorStore
    k: int = 5
    metadata_filters: dict | None = None

    class Config:
        arbitrary_types_allowed = True

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        """Execute the BM25 full-text search on Pinecone."""
        return self.store.search_children_bm25(
            query=query, limit=self.k, metadata_filters=self.metadata_filters
        )
