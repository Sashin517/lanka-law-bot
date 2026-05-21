from __future__ import annotations

import logging
from uuid import NAMESPACE_URL, uuid5

from langchain_core.documents import Document

from app.core.config import settings
from app.services.ingestion.legal_chunker import LegalChunk

logger = logging.getLogger(__name__)


class UserDocumentVectorStore:
    def __init__(self) -> None:
        if not settings.PINECONE_API_KEY:
            raise RuntimeError("PINECONE_API_KEY is required for user document ingestion.")
        if not settings.PINECONE_INDEX_HOST:
            raise RuntimeError("PINECONE_INDEX_HOST is required for user document ingestion.")
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
        """Upsert chunks into Pinecone using integrated inference.

        Pinecone will automatically embed the ``text`` field via the
        ``llama-text-embed-v2`` model configured on the index.

        Returns the list of record IDs (one per chunk).
        """
        records: list[dict] = []
        record_ids: list[str] = []

        for chunk in chunks:
            record_id = self.record_id(
                chunk.metadata.document_id,
                chunk.metadata.chunk_id,
                chunk.metadata.text_hash,
            )
            record_ids.append(record_id)

            # Build the record payload.  The ``text`` field is the one
            # mapped in Pinecone's field_map for integrated embedding.
            metadata = self._pinecone_metadata(chunk.metadata.model_dump())
            record = {
                "_id": record_id,
                "text": chunk.text,
                **metadata,
            }
            records.append(record)

        namespace = settings.PINECONE_NAMESPACE
        for start in range(0, len(records), settings.INGESTION_BATCH_SIZE):
            batch = records[start: start + settings.INGESTION_BATCH_SIZE]
            self._index.upsert_records(
                namespace=namespace,
                records=batch,
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

        results = self._index.search_records(
            namespace=settings.PINECONE_NAMESPACE,
            inputs={"text": query},
            top_k=limit,
            filter=query_filter,
        )
        return [self._hit_to_document(hit) for hit in (results.result.hits if results.result else [])]

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
                response.pagination.get("next")
                if response.pagination
                else None
            )
            if not pagination_token:
                break

        return documents[:limit]

    def fetch_parent(
        self,
        parent_id: str,
        tenant_id: str,
        user_id: str,
        document_id: str,
    ) -> Document | None:
        query_filter = {
            "tenant_id": {"$eq": tenant_id},
            "user_id": {"$eq": user_id},
            "document_id": {"$eq": document_id},
            "chunk_type": {"$eq": "parent"},
            "chunk_id": {"$eq": parent_id},
        }

        # Use search_records with a minimal query to fetch the parent.
        # The query text is set to a generic legal phrase; the filter
        # guarantees we get the exact parent record back.
        results = self._index.search_records(
            namespace=settings.PINECONE_NAMESPACE,
            inputs={"text": "legal clause section"},
            top_k=1,
            filter=query_filter,
        )
        hits = results.result.hits if results.result else []
        return self._hit_to_document(hits[0]) if hits else None

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
