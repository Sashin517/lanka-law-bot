from __future__ import annotations

import logging
import time

from app.core.config import settings

logger = logging.getLogger(__name__)


class VoyageEmbeddingService:
    def __init__(self) -> None:
        if not settings.VOYAGE_API_KEY:
            raise RuntimeError("VOYAGE_API_KEY is required for user document ingestion.")
        try:
            import voyageai
        except ImportError as exc:
            raise RuntimeError("voyageai is not installed. Install backend requirements.") from exc

        self._client = voyageai.Client(api_key=settings.VOYAGE_API_KEY)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        embeddings: list[list[float]] = []
        batch_size = min(settings.INGESTION_BATCH_SIZE, 256)
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            embeddings.extend(self._embed_batch_with_retry(batch))
        return embeddings

    def _embed_batch_with_retry(self, texts: list[str]) -> list[list[float]]:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                result = self._client.embed(
                    texts,
                    model=settings.VOYAGE_EMBEDDING_MODEL,
                    input_type=settings.VOYAGE_EMBEDDING_INPUT_TYPE,
                    truncation=True,
                    output_dtype="float",
                )
                vectors = result.embeddings
                self._validate_vectors(vectors)
                return vectors
            except Exception as exc:
                last_error = exc
                logger.warning("Voyage embedding attempt %d failed: %s", attempt + 1, exc)
                time.sleep(2**attempt)
        raise RuntimeError(f"Voyage embedding failed after retries: {last_error}") from last_error

    @staticmethod
    def _validate_vectors(vectors: list[list[float]]) -> None:
        for vector in vectors:
            if len(vector) != settings.VOYAGE_EMBEDDING_DIMENSION:
                raise ValueError(
                    "Unexpected Voyage embedding dimension: "
                    f"{len(vector)} != {settings.VOYAGE_EMBEDDING_DIMENSION}"
                )
