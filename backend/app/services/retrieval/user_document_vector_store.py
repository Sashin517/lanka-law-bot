from __future__ import annotations

import logging
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from langchain_core.documents import Document

from app.core.config import settings
from app.services.ingestion.legal_chunker import LegalChunk

logger = logging.getLogger(__name__)


class UserDocumentVectorStore:
    def __init__(self) -> None:
        if not settings.PINECONE_API_KEY:
            raise RuntimeError(
                "PINECONE_API_KEY is required for user document ingestion."
            )
        if not settings.PINECONE_INDEX_HOST:
            raise RuntimeError(
                "PINECONE_INDEX_HOST is required for user document ingestion."
            )
        try:
            from pinecone import Pinecone
        except ImportError as exc:
            raise RuntimeError(
                "pinecone is not installed. Install backend requirements."
            ) from exc

        self._pc = Pinecone(api_key=settings.PINECONE_API_KEY)
        self._index = self._pc.Index(host=settings.PINECONE_INDEX_HOST)
        self.collection = settings.PINECONE_INDEX_NAME

    # ------------------------------------------------------------------
    # Collection / index readiness
    # ------------------------------------------------------------------
    def ensure_collection(self) -> None:
        """Verify the Pinecone index exists and is ready.

        With Pinecone's integrated inference the index and its embedding
        model are configured through the Pinecone dashboard, so there is
        nothing to create here.  This method simply checks connectivity.
        """
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

    # ------------------------------------------------------------------
    # Upsert (uses Pinecone integrated inference – no external embeddings)
    # ------------------------------------------------------------------
    def upsert_chunks(
        self,
        chunks: list[LegalChunk],
    ) -> list[str]:
        """Upsert chunks into Pinecone using client-side Jina API embeddings.

        Returns the list of record IDs (one per chunk).
        """
        record_ids: list[str] = []
        texts_to_embed: list[str] = []
        chunk_metadatas: list[dict] = []

        for chunk in chunks:
            record_id = self.record_id(
                chunk.metadata.document_id,
                chunk.metadata.chunk_id,
                chunk.metadata.text_hash,
            )
            record_ids.append(record_id)
            texts_to_embed.append(chunk.text)

            metadata = self._pinecone_metadata(chunk.metadata.model_dump())
            metadata["text"] = chunk.text
            chunk_metadatas.append(metadata)

        # Generate Jina embeddings
        from app.services.retrieval.jina_embedding_service import (
            get_jina_embedding_service,
        )

        embed_service = get_jina_embedding_service()
        vectors = embed_service.embed_documents(texts_to_embed)

        records: list[dict] = []
        for r_id, vector, metadata in zip(record_ids, vectors, chunk_metadatas):
            records.append({"id": r_id, "values": vector, "metadata": metadata})

        namespace = settings.PINECONE_NAMESPACE
        upsert_timeout = getattr(settings, "PINECONE_UPSERT_TIMEOUT", 60.0)
        for start in range(0, len(records), settings.INGESTION_BATCH_SIZE):
            batch = records[start : start + settings.INGESTION_BATCH_SIZE]
            self._index.upsert(
                namespace=namespace,
                vectors=batch,
                timeout=upsert_timeout,
            )

        return record_ids

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------
    def delete_document(self, document_id: str, tenant_id: str) -> None:
        """Delete all records belonging to a specific document."""
        try:
            self._index.delete(
                namespace=settings.PINECONE_NAMESPACE,
                filter={
                    "tenant_id": {"$eq": tenant_id},
                    "document_id": {"$eq": document_id},
                },
                timeout=30.0,
            )
        except Exception as exc:
            if self._is_missing_namespace_error(exc):
                logger.info(
                    "Skipping delete for document=%s in namespace='%s' because it does not exist yet.",
                    document_id,
                    settings.PINECONE_NAMESPACE,
                )
                return
            raise

    # ------------------------------------------------------------------
    # Search (integrated inference – send raw query text)
    # ------------------------------------------------------------------
    def search_children(
        self,
        query: str,
        document_ids: list[str],
        tenant_id: str,
        user_id: str,
        matter_id: str | None = None,
        limit: int = 20,
    ) -> list[Document]:
        query_filter = self._chunk_filter(
            tenant_id=tenant_id,
            user_id=user_id,
            document_ids=document_ids,
            chunk_type="child",
            matter_id=matter_id,
        )

        # Generate Jina embedding for the search query
        from app.services.retrieval.jina_embedding_service import (
            get_jina_embedding_service,
        )

        embed_service = get_jina_embedding_service()
        query_vector = embed_service.embed_query(query)

        results = self._index.query(
            namespace=settings.PINECONE_NAMESPACE,
            vector=query_vector,
            top_k=limit,
            filter=query_filter,
            include_metadata=True,
        )
        return [
            self._query_match_to_document(match) for match in (results.matches or [])
        ]

    def load_child_documents_for_bm25(
        self,
        document_ids: list[str],
        tenant_id: str,
        user_id: str,
        matter_id: str | None = None,
        limit: int = 5000,
    ) -> list[Document]:
        """Load child chunk documents for BM25 sparse search.

        Uses ``fetch_by_metadata`` to paginate through all matching
        child chunks.
        """
        meta_filter = self._chunk_filter(
            tenant_id=tenant_id,
            user_id=user_id,
            document_ids=document_ids,
            chunk_type="child",
            matter_id=matter_id,
        )
        documents: list[Document] = []
        pagination_token: str | None = None

        while len(documents) < limit:
            batch_limit = min(100, limit - len(documents))
            kwargs: dict = {
                "namespace": settings.PINECONE_NAMESPACE,
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

    def fetch_parents_batch(
        self,
        parent_ids: list[str],
        tenant_id: str,
        user_id: str,
        document_ids: list[str] | None = None,
    ) -> dict[str, Document]:
        """Batch fetch parent chunks in a single Pinecone query call.

        Filters by chunk_id $in parent_ids without in-memory caching.
        """
        if not parent_ids:
            return {}

        unique_pids = list(dict.fromkeys(pid for pid in parent_ids if pid))
        if not unique_pids:
            return {}

        query_filter: dict[str, Any] = {
            "tenant_id": {"$eq": tenant_id},
            "user_id": {"$eq": user_id},
            "chunk_type": {"$eq": "parent"},
        }

        if len(unique_pids) == 1:
            query_filter["chunk_id"] = {"$eq": unique_pids[0]}
        else:
            query_filter["chunk_id"] = {"$in": unique_pids}

        if document_ids:
            clean_doc_ids = [d for d in document_ids if d]
            if len(clean_doc_ids) == 1:
                query_filter["document_id"] = {"$eq": clean_doc_ids[0]}
            elif clean_doc_ids:
                query_filter["document_id"] = {"$in": clean_doc_ids}

        zero_vector = [0.0] * settings.PINECONE_EMBEDDING_DIMENSION
        results = self._index.query(
            namespace=settings.PINECONE_NAMESPACE,
            vector=zero_vector,
            top_k=max(len(unique_pids), 10),
            filter=query_filter,
            include_metadata=True,
        )

        matches = results.matches or []
        doc_map: dict[str, Document] = {}
        for match in matches:
            doc = self._query_match_to_document(match)
            chunk_id = doc.metadata.get("chunk_id")
            if chunk_id:
                doc_map[chunk_id] = doc

        return doc_map

    def fetch_parent(
        self,
        parent_id: str,
        tenant_id: str,
        user_id: str,
        document_id: str,
    ) -> Document | None:
        if not parent_id:
            return None
        doc_map = self.fetch_parents_batch(
            parent_ids=[parent_id],
            tenant_id=tenant_id,
            user_id=user_id,
            document_ids=[document_id] if document_id else None,
        )
        return doc_map.get(parent_id)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def record_id(document_id: str, chunk_id: str, text_hash: str) -> str:
        """Deterministic record ID for idempotent upserts."""
        return str(uuid5(NAMESPACE_URL, f"{document_id}:{chunk_id}:{text_hash}"))

    # Keep backward-compatible alias used by the ingestion worker
    point_id = record_id

    @staticmethod
    def _chunk_filter(
        tenant_id: str,
        user_id: str,
        document_ids: list[str],
        chunk_type: str,
        matter_id: str | None = None,
    ) -> dict:
        """Build a Pinecone metadata filter dict."""
        conditions: dict = {
            "tenant_id": {"$eq": tenant_id},
            "user_id": {"$eq": user_id},
            "chunk_type": {"$eq": chunk_type},
        }
        if len(document_ids) == 1:
            conditions["document_id"] = {"$eq": document_ids[0]}
        else:
            conditions["document_id"] = {"$in": document_ids}

        if matter_id:
            conditions["matter_id"] = {"$eq": matter_id}

        return conditions

    @staticmethod
    def _hit_to_document(hit) -> Document:
        """Convert a Pinecone search hit to a LangChain Document."""
        fields = dict(hit.fields or {})
        text = fields.pop("text", "") or ""
        fields["point_id"] = hit.id
        return Document(page_content=text, metadata=fields)

    @staticmethod
    def _query_match_to_document(match) -> Document:
        """Convert a standard Pinecone query match to a LangChain Document."""
        metadata = dict(match.metadata or {})
        text = metadata.pop("text", "") or ""
        metadata["point_id"] = match.id
        return Document(page_content=text, metadata=metadata)

    @staticmethod
    def _is_missing_namespace_error(exc: Exception) -> bool:
        status = getattr(exc, "status", None)
        status_code = getattr(exc, "status_code", None)
        message = str(exc).lower()
        type_name = type(exc).__name__.lower()
        return (
            ("namespace not found" in message)
            or status == 404
            or status_code == 404
            or ("notfound" in type_name and "namespace" in message)
        )

    @staticmethod
    def _pinecone_metadata(metadata: dict) -> dict:
        sanitized: dict = {}
        for key, value in metadata.items():
            if value is None:
                continue
            if isinstance(value, list):
                sanitized[key] = [str(item) for item in value if item is not None]
                continue
            sanitized[key] = value
        return sanitized
