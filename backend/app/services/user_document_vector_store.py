from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from app.core.config import settings
from app.services.legal_chunker import LegalChunk


class UserDocumentVectorStore:
    def __init__(self) -> None:
        if not settings.QDRANT_URL:
            raise RuntimeError("QDRANT_URL is required for user document ingestion.")
        if not settings.QDRANT_API_KEY:
            raise RuntimeError("QDRANT_API_KEY is required for user document ingestion.")
        try:
            from qdrant_client import QdrantClient
        except ImportError as exc:
            raise RuntimeError("qdrant-client is not installed. Install backend requirements.") from exc

        self._client = QdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY,
        )
        self.collection = settings.QDRANT_COLLECTION_USER_DOCS

    def ensure_collection(self) -> None:
        from qdrant_client.http import models

        existing = {collection.name for collection in self._client.get_collections().collections}
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

    @staticmethod
    def point_id(document_id: str, chunk_id: str, text_hash: str) -> str:
        return str(uuid5(NAMESPACE_URL, f"{document_id}:{chunk_id}:{text_hash}"))
