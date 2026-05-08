from __future__ import annotations

import logging
from typing import Any

import numpy as np
import langchain_community.utils.math as lc_math
from langchain_community.retrievers import BM25Retriever
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.cross_encoders import HuggingFaceCrossEncoder
from langchain_classic.retrievers.contextual_compression import (
    ContextualCompressionRetriever,
)
from langchain_classic.retrievers.document_compressors.cross_encoder_rerank import (
    CrossEncoderReranker,
)
from langchain_classic.retrievers.ensemble import EnsembleRetriever

from app.core.config import settings

logger = logging.getLogger(__name__)


def _patched_cosine_similarity(X: Any, Y: Any) -> np.ndarray:
    X = np.array(X, dtype=np.float32)
    Y = np.array(Y, dtype=np.float32)
    X_norm = X / np.linalg.norm(X, axis=1, keepdims=True)
    Y_norm = Y / np.linalg.norm(Y, axis=1, keepdims=True)
    return np.dot(X_norm, Y_norm.T)


lc_math.cosine_similarity = _patched_cosine_similarity


class RetrievalService:
    """
    Hybrid retrieval pipeline:

    1. Dense search  (ChromaDB, children only)
    2. Sparse search (BM25, children only)
    3. Reciprocal Rank Fusion  (merge + deduplicate)
    4. Cross-Encoder Re-Ranking (precision scoring)
    5. Parent chunk expansion  (from ChromaDB by citation_id)
    """

    def __init__(self) -> None:
        logger.info("Initialising RetrievalService …")

        self._embeddings = HuggingFaceEmbeddings(
            model_name=settings.EMBEDDING_MODEL,
        )
        self._chroma = Chroma(
            persist_directory=settings.CHROMA_PATH,
            embedding_function=self._embeddings,
        )

        child_docs = self._load_children_for_bm25()
        self._has_new_schema = len(child_docs) > 0

        if self._has_new_schema:
            logger.info("New schema detected — using chunk_type filters.")
            dense_filter = {"chunk_type": "child"}
        else:
            # Fallback: old DB without chunk_type metadata — load ALL docs
            logger.warning(
                "No child chunks found — old DB schema detected. "
                "Loading all documents without chunk_type filter. "
                "Run the ingestion pipeline to enable parent-child retrieval."
            )
            child_docs = self._load_all_documents()
            dense_filter = None

        # --- Dense retriever ---
        search_kwargs: dict = {"k": settings.RETRIEVAL_CANDIDATES_K}
        if dense_filter:
            search_kwargs["filter"] = dense_filter
        self._dense_retriever = self._chroma.as_retriever(
            search_kwargs=search_kwargs,
        )

        if child_docs:
            self._bm25_retriever = BM25Retriever.from_documents(
                child_docs,
                k=settings.RETRIEVAL_CANDIDATES_K,
            )
            logger.info("BM25 index built from %d chunks.", len(child_docs))

            self._hybrid_retriever = EnsembleRetriever(
                retrievers=[self._dense_retriever, self._bm25_retriever],
                weights=[settings.DENSE_WEIGHT, settings.SPARSE_WEIGHT],
            )
        else:
            logger.warning("No documents in DB — BM25 and hybrid retrieval disabled.")
            self._bm25_retriever = None
            self._hybrid_retriever = None

        cross_encoder = HuggingFaceCrossEncoder(
            model_name=settings.RERANKER_MODEL,
        )
        reranker = CrossEncoderReranker(
            model=cross_encoder,
            top_n=settings.RERANKER_TOP_N,
        )
        if self._hybrid_retriever:
            self._reranked_retriever = ContextualCompressionRetriever(
                base_compressor=reranker,
                base_retriever=self._hybrid_retriever,
            )
        else:
            self._reranked_retriever = None

        logger.info("RetrievalService ready.")

    def search(
        self,
        query: str,
        top_k: int = 5,
        expand_parents: bool = True,
    ) -> list[dict]:
        """
        Execute hybrid search → re-rank → deduplicate → parent expansion.

        Returns a list of dicts, each containing:
            - ``child``    : Document  — the matched child chunk
            - ``parent``   : Document | None — expanded parent context
            - ``metadata`` : dict — full structured metadata
        """
        candidates: list[Document] = []
        if self._reranked_retriever:
            try:
                candidates = self._reranked_retriever.invoke(query)
            except Exception:
                logger.exception("Re-ranked retrieval failed; trying hybrid.")
        if not candidates and self._hybrid_retriever:
            try:
                candidates = self._hybrid_retriever.invoke(query)
            except Exception:
                logger.exception("Hybrid retrieval failed; trying dense only.")
        if not candidates:
            candidates = self._dense_retriever.invoke(query)

        # 2. Deduplicate by citation_id
        seen: set[str] = set()
        unique: list[Document] = []
        for doc in candidates:
            cid = doc.metadata.get("citation_id", str(id(doc)))
            if cid not in seen:
                seen.add(cid)
                unique.append(doc)

        # 3. Expand to parents
        results: list[dict] = []
        for child in unique[:top_k]:
            parent = None
            if expand_parents:
                parent_id = child.metadata.get("parent_id")
                if parent_id:
                    parent = self._fetch_parent(parent_id)

            results.append(
                {
                    "child": child,
                    "parent": parent,
                    "metadata": child.metadata,
                }
            )

        logger.info(
            "Retrieved %d results for query: '%s'",
            len(results),
            query[:80],
        )
        return results

    def _load_children_for_bm25(self) -> list[Document]:
        """Load all child chunks from ChromaDB to build the BM25 index."""
        results = self._chroma.get(
            where={"chunk_type": "child"},
            include=["documents", "metadatas"],
        )
        documents: list[Document] = []
        if results and results.get("documents"):
            for text, meta in zip(results["documents"], results["metadatas"]):
                documents.append(Document(page_content=text, metadata=meta))
        return documents

    def _load_all_documents(self) -> list[Document]:
        """Load ALL documents from ChromaDB (fallback for old DB without chunk_type)."""
        results = self._chroma.get(
            include=["documents", "metadatas"],
        )
        documents: list[Document] = []
        if results and results.get("documents"):
            for text, meta in zip(results["documents"], results["metadatas"]):
                documents.append(Document(page_content=text, metadata=meta))
        return documents

    def _fetch_parent(self, parent_citation_id: str) -> Document | None:
        """Fetch a single parent chunk from ChromaDB by its citation_id."""
        try:
            results = self._chroma.get(
                where={
                    "$and": [
                        {"chunk_type": "parent"},
                        {"citation_id": parent_citation_id},
                    ]
                },
                include=["documents", "metadatas"],
            )
            if results and results.get("documents"):
                return Document(
                    page_content=results["documents"][0],
                    metadata=results["metadatas"][0],
                )
        except Exception:
            logger.warning(
                "Failed to fetch parent chunk: %s",
                parent_citation_id,
            )
        return None
