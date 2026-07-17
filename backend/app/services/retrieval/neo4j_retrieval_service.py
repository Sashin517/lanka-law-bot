"""
Neo4j GraphRAG Hybrid Retrieval Service.
Implements vector search, full-text search, Cypher graph traversal,
Weighted Reciprocal Rank Fusion (WRRF) with pre-scoring, 2-layer deduplication,
cross-encoder re-ranking, and parent context expansion.
"""
from __future__ import annotations

import logging
import numpy as np
from numpy.linalg import norm
from typing import Any, Dict, List, Optional

from langchain_community.cross_encoders import HuggingFaceCrossEncoder
from langchain_core.documents import Document
from neo4j import GraphDatabase


from app.core.config import settings
from app.services.retrieval.neo4j_graph_store import Neo4jGraphStore
from app.services.retrieval.jina_embedding_service import get_jina_embedding_service
from app.services.retrieval.retrieval_fusion import retrieval_dedup_key

logger = logging.getLogger(__name__)


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Computes cosine similarity between two numpy vectors."""
    val = float(np.dot(a, b) / (norm(a) * norm(b) + 1e-10))
    return val


class Neo4jRetrievalService:
    """Handles hybrid search (dense + sparse + graph traversal) and post-processing."""

    def __init__(self) -> None:
        logger.info("Initializing Neo4jRetrievalService...")
        self._driver = GraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        )
        self._store = Neo4jGraphStore(self._driver)

        # Mirror the exact same cross-encoder setup from retrieval_service.py
        logger.info("Loading Cross-Encoder reranker model '%s'...", settings.RERANKER_MODEL)
        self._cross_encoder = HuggingFaceCrossEncoder(
            model_name=settings.RERANKER_MODEL,
        )

    def close(self) -> None:
        self._driver.close()

    def score_and_rank_graph_results(
        self,
        graph_docs: List[Document],
        query_embedding: List[float],
    ) -> List[Document]:
        """Pre-score unordered graph traversal results using cosine similarity."""
        query_vec = np.array(query_embedding)
        scored: List[tuple[float, Document]] = []

        for doc in graph_docs:
            doc_embedding = doc.metadata.get("embedding")
            if doc_embedding is not None:
                sim = _cosine_similarity(query_vec, np.array(doc_embedding))
            else:
                sim = 0.5  # Neutral default score

            doc.metadata["graph_relevance_score"] = sim
            scored.append((sim, doc))

        # Sort descending by similarity
        scored.sort(key=lambda x: x[0], reverse=True)
        return [doc for _, doc in scored]

    def weighted_reciprocal_rank_fusion(
        self,
        ranked_lists: List[List[Document]],
        weights: List[float],
        k: int = 60,
    ) -> List[Document]:
        """WRRF: Combines ranked lists by positions using a weight multiplier."""
        scores: Dict[str, float] = {}
        docs_by_key: Dict[str, Document] = {}

        for weight, ranked_list in zip(weights, ranked_lists):
            for rank, doc in enumerate(ranked_list, start=1):
                key = retrieval_dedup_key(doc)
                scores[key] = scores.get(key, 0.0) + weight / (k + rank)
                docs_by_key.setdefault(key, doc)

        return [
            docs_by_key[key]
            for key, _ in sorted(scores.items(), key=lambda x: x[1], reverse=True)
        ]

    def deduplicate_results(self, candidates: List[Document]) -> List[Document]:
        """Two-layer deduplication based on chunk_id and full SHA256 text_hash."""
        seen_chunk_ids = set()
        seen_text_hashes = set()
        unique = []

        for doc in candidates:
            meta = doc.metadata or {}
            
            chunk_id = meta.get("chunk_id", "")
            if chunk_id and chunk_id in seen_chunk_ids:
                continue
            
            text_hash = meta.get("text_hash", "")
            if text_hash and text_hash in seen_text_hashes:
                continue

            if chunk_id:
                seen_chunk_ids.add(chunk_id)
            if text_hash:
                seen_text_hashes.add(text_hash)
            unique.append(doc)

        return unique

    def rerank_candidates(self, candidates: List[Document], query: str) -> List[Document]:
        """Re-rank candidate documents using MS-MARCO Cross-Encoder."""
        if not candidates:
            return []

        # Format inputs for cross-encoder model: list of (query, doc_text) pairs
        pairs = [(query, doc.page_content) for doc in candidates]
        scores = self._cross_encoder.score(pairs)

        # Attach scores to metadata
        for doc, score in zip(candidates, scores):
            doc.metadata["relevance_score"] = float(score)

        # Sort descending by cross-encoder score
        candidates.sort(key=lambda x: x.metadata["relevance_score"], reverse=True)
        return candidates

    def search(
        self,
        query: str,
        top_k: int = 10,
        expand_parents: bool = True,
        year_filter: Optional[int] = None,
        act_name_filter: Optional[str] = None,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """
        Execute Hybrid Search (Vector + FTS + Cypher Graph Traversal),
        fuses via WRRF, reranks, deduplicates, and expands parents.
        """
        # Embed query via Jina
        embed_service = get_jina_embedding_service()
        query_embedding = embed_service.embed_query(query)

        # 1. Vector Dense Search
        vector_results = self._store.vector_search(
            query_embedding=query_embedding,
            top_k=settings.NEO4J_VECTOR_CANDIDATES_K,
            year_filter=year_filter,
            source_type_filter=kwargs.get("source_type_filter"),
        )

        # 2. Full-Text Search
        fts_results = self._store.fulltext_search(
            query_text=query,
            top_k=settings.NEO4J_FTS_CANDIDATES_K,
            year_filter=year_filter,
        )

        # 3. Cypher Graph Traversal (using top vector + FTS chunk IDs as seeds)
        seed_ids = []
        for doc in (vector_results[:5] + fts_results[:5]):
            cid = doc.metadata.get("chunk_id")
            if cid:
                seed_ids.append(cid)

        raw_graph_results = self._store.graph_traversal(
            seed_chunk_ids=seed_ids,
            limit=settings.NEO4J_GRAPH_TRAVERSAL_LIMIT,
        )
        
        # Pre-score graph results before RRF
        graph_results = self.score_and_rank_graph_results(raw_graph_results, query_embedding)

        # 4. WRRF Fusion
        fused_candidates = self.weighted_reciprocal_rank_fusion(
            ranked_lists=[vector_results, fts_results, graph_results],
            weights=[
                settings.NEO4J_VECTOR_WEIGHT,
                settings.NEO4J_FTS_WEIGHT,
                settings.NEO4J_GRAPH_WEIGHT,
            ]
        )

        # 5. Two-layer Deduplication
        deduped = self.deduplicate_results(fused_candidates)

        # 6. Metadata Soft Filters (Act Name matching)
        if act_name_filter:
            deduped = self._soft_filter_act_name(deduped, act_name_filter)

        # 7. Cross-Encoder Reranking
        reranked = self.rerank_candidates(deduped, query)

        # 8. Parent context expansion
        results = []
        for child in reranked[:top_k]:
            parent = None
            if expand_parents:
                parent_id = child.metadata.get("parent_chunk_id") or child.metadata.get("parent_id")
                if parent_id:
                    parent = self._store.fetch_parent(parent_id)

            results.append({
                "child": child,
                "parent": parent,
                "metadata": child.metadata,
            })

        logger.info(
            "GraphRAG search returned %d results for query: '%s'",
            len(results),
            query[:80],
        )
        return results

    def _soft_filter_act_name(self, candidates: List[Document], filter_name: Any) -> List[Document]:
        """Soft-filter to prioritize candidates matching the target act name."""
        if not filter_name:
            return candidates
            
        targets = []
        if isinstance(filter_name, list):
            targets = [str(t).lower().strip() for t in filter_name if t]
        else:
            targets = [str(filter_name).lower().strip()]

        matched = []
        others = []
        for doc in candidates:
            title = (doc.metadata.get("title") or "").lower()
            if any(t in title for t in targets):
                matched.append(doc)
            else:
                others.append(doc)
        
        # Bring matched to the top, followed by others
        return matched + others


_instance: Optional[Neo4jRetrievalService] = None


def get_neo4j_retrieval_service() -> Neo4jRetrievalService:
    """Singleton getter for Neo4jRetrievalService."""
    global _instance
    if _instance is None:
        _instance = Neo4jRetrievalService()
    return _instance
