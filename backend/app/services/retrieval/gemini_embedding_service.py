"""
Jina AI Embedding Service.
Generates embeddings using Jina AI's cloud-hosted jina-embeddings-v4 model.
Conforms to task-specific tasks for asymmetric search.
"""
from __future__ import annotations

import logging
import os
import time
import httpx
from typing import Any, Dict, List, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


class GeminiEmbeddingService:
    """Service to fetch text embeddings from Jina AI using jina-embeddings-v4."""

    def __init__(self) -> None:
        self._model = settings.NEO4J_EMBEDDING_MODEL  # "jina-embeddings-v4"
        self._dim = settings.NEO4J_EMBEDDING_DIMENSION  # 2048

    def _embed_with_retry(self, input_texts: List[str], task: str, max_retries: int = 5) -> List[List[float]]:
        # Get your Jina AI API key for free: https://jina.ai/?sui=apikey
        api_key = settings.JINA_API_KEY or os.environ.get("JINA_API_KEY", "")
        if not api_key:
            logger.error("JINA_API_KEY is not set! Please set the JINA_API_KEY environment variable.")
            return [[0.0] * self._dim for _ in range(len(input_texts))]

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        data = {
            "model": self._model,
            "input": input_texts,
            "task": task,
            "dimensions": self._dim
        }

        backoff = 2.0
        for attempt in range(max_retries):
            try:
                response = httpx.post("https://api.jina.ai/v1/embeddings", json=data, headers=headers, timeout=60.0)
                if response.status_code == 200:
                    res_json = response.json()
                    sorted_data = sorted(res_json["data"], key=lambda x: x["index"])
                    return [item["embedding"] for item in sorted_data]
                elif response.status_code == 429:
                    logger.warning("Jina AI rate limit hit (429)! Retrying in %.2f seconds...", backoff)
                    time.sleep(backoff)
                    backoff *= 2.0
                else:
                    logger.warning("Jina AI API returned error status %d: %s", response.status_code, response.text)
                    time.sleep(backoff)
                    backoff *= 2.0
            except Exception as e:
                logger.warning("Jina AI request exception: %s. Retrying...", e)
                time.sleep(backoff)
                backoff *= 2.0

        # Return zero vector fallbacks if failed
        return [[0.0] * self._dim for _ in range(len(input_texts))]

    def embed_query(self, query: str) -> List[float]:
        """Embeds a single query using the asymmetric search query prefix/task."""
        try:
            embeddings = self._embed_with_retry([query], task="retrieval.query")
            return embeddings[0]
        except Exception as exc:
            logger.exception("Jina query embedding generation failed: %s", exc)
            return [0.0] * self._dim

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embeds a list of document chunks using the asymmetric search passage prefix/task."""
        if not texts:
            return []
        try:
            embeddings = []
            # Jina API can handle batch inputs. We split them into safe batch sizes of 16.
            batch_size = 16
            for i in range(0, len(texts), batch_size):
                batch = texts[i : i + batch_size]
                embeddings.extend(self._embed_with_retry(batch, task="retrieval.passage"))
            return embeddings
        except Exception as exc:
            logger.exception("Jina document embedding generation failed: %s", exc)
            return [[0.0] * self._dim for _ in range(len(texts))]

    def embed_documents_batch(self, docs: List[Dict[str, Any]]) -> List[List[float]]:
        """
        Embeds a batch of document texts.
        """
        if not docs:
            return []

        formatted_contents = []
        for doc in docs:
            title = doc.get("title") or "none"
            formatted_contents.append(f"title: {title} | text: {doc['text']}")

        try:
            return self._embed_with_retry(formatted_contents, task="retrieval.passage")
        except Exception as exc:
            logger.exception("Jina batch document embedding generation failed: %s", exc)
            return [[0.0] * self._dim for _ in range(len(docs))]


_instance: Optional[GeminiEmbeddingService] = None


def get_gemini_embedding_service() -> GeminiEmbeddingService:
    """Singleton getter for GeminiEmbeddingService (reimplemented with Jina AI)."""
    global _instance
    if _instance is None:
        _instance = GeminiEmbeddingService()
    return _instance

