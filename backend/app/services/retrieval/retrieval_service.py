from __future__ import annotations

import logging
from typing import Any

import numpy as np
import langchain_community.utils.math as lc_math
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from langchain_community.cross_encoders import HuggingFaceCrossEncoder
from langchain_classic.retrievers.contextual_compression import (
    ContextualCompressionRetriever,
)
from langchain_classic.retrievers.document_compressors.cross_encoder_rerank import (
    CrossEncoderReranker,
)
from langchain_classic.retrievers.ensemble import EnsembleRetriever

from app.core.config import settings
from app.services.retrieval.legal_vector_store import LegalVectorStore, PineconeLegalRetriever

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
    Hybrid retrieval pipeline (Pinecone-backed):

    1. Dense search  (Pinecone lawdex-legal-index, children only)
    2. Sparse search (BM25, children only)
    3. Reciprocal Rank Fusion  (merge + deduplicate)
    4. Cross-Encoder Re-Ranking (precision scoring)
    5. Parent chunk expansion  (from Pinecone by chunk_id)
    """

    def __init__(self) -> None:
        logger.info("Initialising RetrievalService …")

        self._legal_store = LegalVectorStore()
        
        # Load all child docs for BM25
        child_docs = self._legal_store.load_children_for_bm25(limit=50000)

        # --- Dense retriever ---
        self._dense_retriever = PineconeLegalRetriever(
            store=self._legal_store,
            k=settings.RETRIEVAL_CANDIDATES_K
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
        year_filter: list[int] | int | None = None,
        act_name_filter: list[str] | str | None = None,
        **kwargs
    ) -> list[dict]:
        """
        Execute hybrid search → re-rank → deduplicate → parent expansion.

        Parameters
        ----------
        year_filter : int | None
            If set, prefer chunks whose ``year`` metadata matches.
        act_name_filter : str | None
            If set, prefer chunks whose ``title`` or ``case_name`` metadata contains this.

        Returns a list of dicts, each containing:
            - ``child``    : Document  — the matched child chunk
            - ``parent``   : Document | None — expanded parent context
            - ``metadata`` : dict — full structured metadata
        """
        disable_bm25 = kwargs.get("disable_bm25", False)
        disable_dense = kwargs.get("disable_dense", False)
        disable_reranking = kwargs.get("disable_reranking", False)

        # 1. Determine base retriever
        if disable_bm25 and disable_dense:
            return []
        elif disable_dense and self._bm25_retriever:
            base_retriever = self._bm25_retriever
        elif disable_bm25:
            base_retriever = self._dense_retriever
        else:
            base_retriever = self._hybrid_retriever or self._dense_retriever

        # 2. Execute retrieval
        candidates: list[Document] = []
        try:
            candidates = base_retriever.invoke(query)
        except Exception:
            logger.exception("Base retrieval failed. Falling back to dense.")
            if base_retriever != self._dense_retriever:
                candidates = self._dense_retriever.invoke(query)

        # 3. Optionally Re-rank
        if not disable_reranking and self._reranked_retriever and candidates:
            try:
                # Use the configured compressor directly to re-rank the candidates
                candidates = self._reranked_retriever.base_compressor.compress_documents(candidates, query)
                candidates = self._prune_low_relevance(candidates)
            except Exception:
                logger.exception("Re-ranking failed. Falling back to base ranking.")

        # 2. Deduplicate by chunk_id AND content fingerprint
        seen_ids: set[str] = set()
        seen_content: set[str] = set()
        unique: list[Document] = []
        for doc in candidates:
            cid = doc.metadata.get("chunk_id", "")
            content_key = doc.page_content[:500].strip()

            # Skip if we have already seen this chunk_id OR this content
            if cid and cid in seen_ids:
                continue
            if content_key in seen_content:
                continue

            if cid:
                seen_ids.add(cid)
            seen_content.add(content_key)
            unique.append(doc)

        # 3. Post-filter by metadata (entity-aware, with fallback)
        if year_filter or act_name_filter:
            y_filters = [year_filter] if isinstance(year_filter, int) else year_filter
            a_filters = [act_name_filter] if isinstance(act_name_filter, str) else act_name_filter
            unique = self._post_filter_metadata(
                unique,
                y_filters,
                a_filters,
            )

        # 4. Expand to parents
        results: list[dict] = []
        for child in unique[:top_k]:
            parent = None
            if expand_parents:
                parent_id = child.metadata.get("parent_id")
                if parent_id:
                    parent = self._legal_store.fetch_parent(parent_id)

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

    def _prune_low_relevance(self, candidates: list[Document]) -> list[Document]:
        """Drop candidates whose cross-encoder score falls below the
        configured threshold.  If pruning would remove *every* result,
        keep at least the top candidate as a safety valve.

        Documents that lack a ``relevance_score`` (e.g. when the reranker
        was bypassed) are always kept.
        """
        threshold = settings.RELEVANCE_SCORE_THRESHOLD
        if threshold <= 0:
            return candidates  # pruning disabled

        pruned: list[Document] = []
        for doc in candidates:
            score = doc.metadata.get("relevance_score")
            if score is not None and score < threshold:
                logger.debug(
                    "Pruned low-relevance chunk (score=%.4f, threshold=%.4f): %s",
                    score,
                    threshold,
                    doc.page_content[:80],
                )
                continue
            pruned.append(doc)

        # Safety valve: never return an empty list
        return pruned if pruned else candidates[:1]

    @staticmethod
    def _post_filter_metadata(
        candidates: list[Document],
        year_filters: list[int] | None,
        act_name_filters: list[str] | None,
    ) -> list[Document]:
        """Filter already-retrieved candidates by metadata constraints using soft-match logic.

        If filtering would produce an empty result set, the original unfiltered list is returned 
        as a safety fallback to prevent breaking the pipeline.
        """
        if not year_filters and not act_name_filters:
            return candidates

        filtered: list[Document] = []
        import re

        for doc in candidates:
            meta = doc.metadata or {}
            
            # Year check
            year_match = True
            if year_filters:
                doc_year = meta.get("year")
                try:
                    if int(doc_year) not in year_filters:
                        year_match = False
                except (TypeError, ValueError):
                    pass # Keep if no parseable year

            # Title / Case Name check
            title_match = True
            if act_name_filters:
                title = (meta.get("title") or meta.get("case_name") or "").lower()
                title_match = False
                for act_name in act_name_filters:
                    if act_name.lower() in title:
                        title_match = True
                        break
                    
                    # Softer match: check if significant words match
                    words = [w.lower() for w in re.findall(r'\b\w{4,}\b', act_name) if w.lower() not in ("ordinance", "amendment")]
                    if words and all(w in title for w in words):
                        title_match = True
                        break

            # If either match holds, we keep the document. This is a soft filter.
            if year_match or title_match:
                if year_filters and not act_name_filters:
                    if year_match: filtered.append(doc)
                elif act_name_filters and not year_filters:
                    if title_match: filtered.append(doc)
                else:
                    # Both provided. If EITHER matches, it's a good candidate.
                    if year_match or title_match:
                        filtered.append(doc)

        if filtered:
            logger.debug(
                "Metadata filter kept %d/%d candidates (years=%s, acts=%s)",
                len(filtered),
                len(candidates),
                year_filters,
                act_name_filters,
            )
            return filtered

        # Fallback: filters too restrictive — return everything
        logger.debug(
            "Metadata filter matched 0/%d candidates — falling back to unfiltered.",
            len(candidates),
        )
        return candidates


# --- Singleton factory (module-level) ---

_instance: RetrievalService | None = None


def get_retrieval_service() -> RetrievalService:
    """Singleton factory for RetrievalService."""
    global _instance
    if _instance is None:
        _instance = RetrievalService()
    return _instance
