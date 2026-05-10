from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from langchain_core.documents import Document

from app.core.config import settings
from app.services.legal_chunker import LegalChunk


class UserDocumentVectorStore:
    def __init__(self) -> None:
        if not settings.QDRANT_URL:
            raise RuntimeError("QDRANT_URL is required for user document ingestion.")
        if not settings.QDRANT_API_KEY:
            raise RuntimeError(
                "QDRANT_API_KEY is required for user document ingestion."
            )
        try:
            from qdrant_client import QdrantClient
        except ImportError as exc:
            raise RuntimeError(
                "qdrant-client is not installed. Install backend requirements."
            ) from exc

        self._client = QdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY,
        )
        self.collection = settings.QDRANT_COLLECTION_USER_DOCS

    def ensure_collection(self) -> None:
        from qdrant_client.http import models

        existing = {
            collection.name for collection in self._client.get_collections().collections
        }
        if self.collection not in existing:
            self._client.create_collection(
                collection_name=self.collection,
                vectors_config=models.VectorParams(
                    size=settings.VOYAGE_EMBEDDING_DIMENSION,
                    distance=models.Distance.COSINE,
                ),
            )
        for field in (
            "tenant_id",
            "user_id",
            "matter_id",
            "document_id",
            "chunk_type",
            "document_type",
            "clause_label",
            "embedding_model",
            "chunk_id",
            "parent_id",
        ):
            try:
                self._client.create_payload_index(
                    collection_name=self.collection,
                    field_name=field,
                    field_schema=models.PayloadSchemaType.KEYWORD,
                )
            except Exception:
                pass

    def upsert_chunks(
        self,
        chunks: list[LegalChunk],
        embeddings: list[list[float]],
    ) -> list[str]:
        from qdrant_client.http import models

        if len(chunks) != len(embeddings):
            raise ValueError("Chunk and embedding counts do not match.")

        points = []
        point_ids: list[str] = []
        for chunk, vector in zip(chunks, embeddings):
            point_id = self.point_id(
                chunk.metadata.document_id,
                chunk.metadata.chunk_id,
                chunk.metadata.text_hash,
            )
            payload = chunk.metadata.model_dump()
            payload["text"] = chunk.text
            point_ids.append(point_id)
            points.append(
                models.PointStruct(
                    id=point_id,
                    vector=vector,
                    payload=payload,
                )
            )

        for start in range(0, len(points), settings.INGESTION_BATCH_SIZE):
            self._client.upsert(
                collection_name=self.collection,
                points=points[start : start + settings.INGESTION_BATCH_SIZE],
                wait=True,
            )
        return point_ids

    def delete_document(self, document_id: str, tenant_id: str) -> None:
        from qdrant_client.http import models

        self._client.delete(
            collection_name=self.collection,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="tenant_id",
                            match=models.MatchValue(value=tenant_id),
                        ),
                        models.FieldCondition(
                            key="document_id",
                            match=models.MatchValue(value=document_id),
                        ),
                    ]
                )
            ),
            wait=True,
        )

    def search_children(
        self,
        query_vector: list[float],
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
        points = self._query_points(
            query_vector=query_vector,
            query_filter=query_filter,
            limit=limit,
        )
        return [self._point_to_document(point) for point in points]

    def load_child_documents_for_bm25(
        self,
        document_ids: list[str],
        tenant_id: str,
        user_id: str,
        matter_id: str | None = None,
        limit: int = 5000,
    ) -> list[Document]:
        query_filter = self._chunk_filter(
            tenant_id=tenant_id,
            user_id=user_id,
            document_ids=document_ids,
            chunk_type="child",
            matter_id=matter_id,
        )
        points = self.fetch_points_by_filter(query_filter=query_filter, limit=limit)
        return [self._point_to_document(point) for point in points]

    def fetch_parent(
        self,
        parent_id: str,
        tenant_id: str,
        user_id: str,
        document_id: str,
    ) -> Document | None:
        from qdrant_client.http import models

        query_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="tenant_id",
                    match=models.MatchValue(value=tenant_id),
                ),
                models.FieldCondition(
                    key="user_id",
                    match=models.MatchValue(value=user_id),
                ),
                models.FieldCondition(
                    key="document_id",
                    match=models.MatchValue(value=document_id),
                ),
                models.FieldCondition(
                    key="chunk_type",
                    match=models.MatchValue(value="parent"),
                ),
                models.FieldCondition(
                    key="chunk_id",
                    match=models.MatchValue(value=parent_id),
                ),
            ]
        )
        points = self.fetch_points_by_filter(query_filter=query_filter, limit=1)
        return self._point_to_document(points[0]) if points else None

    def fetch_points_by_filter(
        self,
        query_filter,
        limit: int,
        with_payload: bool = True,
    ) -> list:
        points: list = []
        next_page = None
        while len(points) < limit:
            batch_limit = min(256, limit - len(points))
            batch, next_page = self._client.scroll(
                collection_name=self.collection,
                scroll_filter=query_filter,
                limit=batch_limit,
                offset=next_page,
                with_payload=with_payload,
                with_vectors=False,
            )
            points.extend(batch)
            if next_page is None or not batch:
                break
        return points

    @staticmethod
    def point_id(document_id: str, chunk_id: str, text_hash: str) -> str:
        return str(uuid5(NAMESPACE_URL, f"{document_id}:{chunk_id}:{text_hash}"))

    def _query_points(
        self, query_vector: list[float], query_filter, limit: int
    ) -> list:
        if hasattr(self._client, "query_points"):
            result = self._client.query_points(
                collection_name=self.collection,
                query=query_vector,
                query_filter=query_filter,
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )
            return list(result.points)

        return self._client.search(
            collection_name=self.collection,
            query_vector=query_vector,
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )

    @staticmethod
    def _chunk_filter(
        tenant_id: str,
        user_id: str,
        document_ids: list[str],
        chunk_type: str,
        matter_id: str | None = None,
    ):
        from qdrant_client.http import models

        must = [
            models.FieldCondition(
                key="tenant_id",
                match=models.MatchValue(value=tenant_id),
            ),
            models.FieldCondition(
                key="user_id",
                match=models.MatchValue(value=user_id),
            ),
            models.FieldCondition(
                key="chunk_type",
                match=models.MatchValue(value=chunk_type),
            ),
        ]
        if len(document_ids) == 1:
            must.append(
                models.FieldCondition(
                    key="document_id",
                    match=models.MatchValue(value=document_ids[0]),
                )
            )
        else:
            must.append(
                models.FieldCondition(
                    key="document_id",
                    match=models.MatchAny(any=document_ids),
                )
            )
        if matter_id:
            must.append(
                models.FieldCondition(
                    key="matter_id",
                    match=models.MatchValue(value=matter_id),
                )
            )
        return models.Filter(must=must)

    @staticmethod
    def _point_to_document(point) -> Document:
        payload = dict(point.payload or {})
        text = payload.pop("text", "") or ""
        payload["point_id"] = str(point.id)
        return Document(page_content=text, metadata=payload)
