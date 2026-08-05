"""Validated Jina embeddings shared by Pinecone, Neo4j and user documents."""

from __future__ import annotations

import logging
import math
import os
import random
import time
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class JinaEmbeddingService:
    """Generate asymmetric Jina embeddings and fail closed on bad vectors."""

    def __init__(self) -> None:
        self._model = settings.JINA_EMBEDDING_MODEL
        self._dim = settings.JINA_EMBEDDING_DIMENSION
        self._client = httpx.Client(timeout=httpx.Timeout(60.0, connect=20.0))

    def _api_key(self) -> str:
        api_key = settings.JINA_API_KEY or os.environ.get("JINA_API_KEY", "")
        if not api_key:
            raise RuntimeError("JINA_API_KEY is required for retrieval embeddings.")
        return api_key

    def _validate_vector(self, vector: Any) -> list[float]:
        if not isinstance(vector, list) or len(vector) != self._dim:
            raise RuntimeError(
                f"Jina returned an invalid dimension; expected {self._dim}."
            )
        converted = [float(value) for value in vector]
        if not all(math.isfinite(value) for value in converted):
            raise RuntimeError("Jina returned a non-finite embedding.")
        if math.sqrt(sum(value * value for value in converted)) == 0:
            raise RuntimeError("Jina returned an all-zero embedding.")
        return converted

    def _embed_with_retry(
        self, input_texts: list[str], task: str, max_retries: int = 5
    ) -> list[list[float]]:
        if not input_texts:
            return []
        headers = {
            "Authorization": f"Bearer {self._api_key()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload = {
            "model": self._model,
            "input": input_texts,
            "task": task,
            "dimensions": self._dim,
        }

        for attempt in range(max_retries):
            try:
                response = self._client.post(
                    "https://api.jina.ai/v1/embeddings",
                    json=payload,
                    headers=headers,
                )
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt == max_retries - 1:
                    raise RuntimeError("Jina embedding request failed after retries.") from exc
                time.sleep(min(30.0, 2**attempt + random.random()))
                continue

            if response.status_code == 200:
                try:
                    rows = sorted(response.json()["data"], key=lambda item: item["index"])
                    vectors = [self._validate_vector(item["embedding"]) for item in rows]
                except (KeyError, TypeError, ValueError) as exc:
                    raise RuntimeError("Jina returned a malformed response.") from exc
                if len(vectors) != len(input_texts):
                    raise RuntimeError(
                        f"Jina returned {len(vectors)} vectors for {len(input_texts)} inputs."
                    )
                return vectors

            if response.status_code in {400, 401, 403, 404, 422}:
                raise RuntimeError(f"Permanent Jina API failure: HTTP {response.status_code}.")
            if attempt == max_retries - 1:
                raise RuntimeError(f"Jina API unavailable: HTTP {response.status_code}.")
            retry_after = response.headers.get("Retry-After")
            try:
                delay = float(retry_after) if retry_after else 2**attempt
            except (TypeError, ValueError):
                delay = 2**attempt
            time.sleep(min(60.0, delay + random.random()))

        raise AssertionError("unreachable")

    def embed_query(self, query: str) -> list[float]:
        if not query or not query.strip():
            raise ValueError("A non-empty query is required for embedding.")
        return self._embed_with_retry([query], task="retrieval.query")[0]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        embeddings: list[list[float]] = []
        for start in range(0, len(texts), 16):
            embeddings.extend(
                self._embed_with_retry(
                    texts[start : start + 16], task="retrieval.passage"
                )
            )
        return embeddings

    def embed_documents_batch(self, docs: list[dict[str, Any]]) -> list[list[float]]:
        formatted = [
            "\n".join(
                part
                for part in (
                    f"title: {doc.get('title')}",
                    f"section: {doc.get('section') or doc.get('section_label')}",
                    f"text: {doc.get('text', '')}",
                )
                if not part.endswith("None")
            )
            for doc in docs
        ]
        return self.embed_documents(formatted)


_instance: JinaEmbeddingService | None = None


def get_jina_embedding_service() -> JinaEmbeddingService:
    global _instance
    if _instance is None:
        _instance = JinaEmbeddingService()
    return _instance
