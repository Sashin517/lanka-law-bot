"""Neo4j GraphRAG hybrid retrieval and evidence-aware graph expansion."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from langchain_community.cross_encoders import HuggingFaceCrossEncoder
from langchain_core.documents import Document
from neo4j import GraphDatabase

from evaluation.ablation import describe_neo4j_effects, retrieval_search_kwargs
from app.core.config import settings
from app.services.retrieval.jina_embedding_service import get_jina_embedding_service
from app.services.retrieval.neo4j_graph_store import Neo4jGraphStore
from app.services.retrieval.retrieval_fusion import retrieval_dedup_key

logger = logging.getLogger(__name__)


class Neo4jRetrievalService:
    """Dense + lexical + authority + graph retrieval with WRRF and reranking."""

    def __init__(self) -> None:
        self._driver = GraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        )
        self._driver.verify_connectivity()
        self._store = Neo4jGraphStore(self._driver)
        self._cross_encoder: HuggingFaceCrossEncoder | None = None

    def close(self) -> None:
        self._driver.close()

    def _reranker(self) -> HuggingFaceCrossEncoder:
        # Lazy loading avoids network/model initialization when reranking is
        # disabled by an ablation or no candidates were retrieved.
        if self._cross_encoder is None:
            logger.info("Loading cross-encoder '%s'", settings.RERANKER_MODEL)
            self._cross_encoder = HuggingFaceCrossEncoder(
                model_name=settings.RERANKER_MODEL
            )
        return self._cross_encoder

    @staticmethod
    def score_and_rank_graph_results(
        graph_docs: List[Document],
    ) -> List[Document]:
        """Rank graph results using evidence/path scores computed in Cypher."""
        for doc in graph_docs:
            doc.metadata["graph_relevance_score"] = float(
                doc.metadata.get("relevance_score", 0.0) or 0.0
            )
        return sorted(
            graph_docs,
            key=lambda doc: doc.metadata["graph_relevance_score"],
            reverse=True,
        )

    @staticmethod
    def weighted_reciprocal_rank_fusion(
        ranked_lists: List[List[Document]],
        weights: List[float],
        k: int = 60,
    ) -> List[Document]:
        if len(ranked_lists) != len(weights):
            raise ValueError("ranked_lists and weights must have equal length")
        scores: Dict[str, float] = {}
        docs_by_key: Dict[str, Document] = {}
        for weight, ranked_list in zip(weights, ranked_lists):
            for rank, doc in enumerate(ranked_list, start=1):
                key = retrieval_dedup_key(doc)
                scores[key] = scores.get(key, 0.0) + weight / (k + rank)
                docs_by_key.setdefault(key, doc)
        return [
            docs_by_key[key]
            for key, _ in sorted(scores.items(), key=lambda item: item[1], reverse=True)
        ]

    @staticmethod
    def deduplicate_results(candidates: List[Document]) -> List[Document]:
        seen_chunk_ids: set[str] = set()
        seen_text_hashes: set[str] = set()
        unique: List[Document] = []
        for doc in candidates:
            metadata = doc.metadata or {}
            chunk_id = metadata.get("chunk_id", "")
            text_hash = metadata.get("text_hash", "")
            if chunk_id and chunk_id in seen_chunk_ids:
                continue
            if text_hash and text_hash in seen_text_hashes:
                continue
            if chunk_id:
                seen_chunk_ids.add(chunk_id)
            if text_hash:
                seen_text_hashes.add(text_hash)
            unique.append(doc)
        return unique

    def rerank_candidates(
        self, candidates: List[Document], query: str
    ) -> List[Document]:
        if not candidates:
            return []
        scores = self._reranker().score(
            [(query, document.page_content) for document in candidates]
        )
        for document, score in zip(candidates, scores):
            document.metadata["relevance_score"] = float(score)
        return sorted(
            candidates,
            key=lambda document: document.metadata["relevance_score"],
            reverse=True,
        )

    def search(
        self,
        query: str,
        top_k: int = 10,
        expand_parents: bool = True,
        year_filter: Optional[int] = None,
        act_name_filter: Any = None,
        as_of: Optional[str] = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """Execute hybrid retrieval against current or explicitly dated law."""
        if top_k < 1:
            raise ValueError("top_k must be positive")
        requested = {**kwargs, "expand_parents": expand_parents}
        effects = self.describe_ablation_effects(requested)
        options = retrieval_search_kwargs(requested)
        disable_dense = options["disable_dense"]
        disable_sparse = options["disable_bm25"]
        graph_enabled = not disable_dense and not disable_sparse
        source_type = kwargs.get("source_type_filter")

        query_embedding = None
        if not disable_dense:
            query_embedding = get_jina_embedding_service().embed_query(query)

        vector_results: List[Document] = []
        if not disable_dense:
            vector_results = self._store.vector_search(
                query_embedding=query_embedding,
                top_k=settings.NEO4J_VECTOR_CANDIDATES_K,
                year_filter=year_filter,
                source_type_filter=source_type,
                as_of=as_of,
            )

        fts_results: List[Document] = []
        if not disable_sparse:
            fts_results = self._store.fulltext_search(
                query_text=query,
                top_k=settings.NEO4J_FTS_CANDIDATES_K,
                year_filter=year_filter,
                source_type_filter=source_type,
                as_of=as_of,
            )

        authority_results: List[Document] = []
        authority_titles = (
            [str(value) for value in act_name_filter if value]
            if isinstance(act_name_filter, list)
            else ([str(act_name_filter)] if act_name_filter else [])
        )
        if authority_titles and not disable_sparse:
            for title in authority_titles:
                authority_results.extend(
                    self._store.authority_search(
                        authority_title=title,
                        top_k=settings.NEO4J_AUTHORITY_CANDIDATES_K,
                        as_of=as_of,
                    )
                )
            authority_results = self.deduplicate_results(authority_results)

        mode = str(kwargs.get("mode") or kwargs.get("query_mode") or "").casefold()
        is_multihop = mode in {"deep_research", "reasoning", "drafting"}
        seed_k = 10 if is_multihop else 5
        authority_k = 5 if is_multihop else 3

        seed_ids = list(
            dict.fromkeys(
                document.metadata.get("chunk_id")
                for document in (
                    vector_results[:seed_k]
                    + fts_results[:seed_k]
                    + authority_results[:authority_k]
                )
                if document.metadata.get("chunk_id")
            )
        )
        graph_results: List[Document] = []
        if graph_enabled and seed_ids:
            graph_results = self.score_and_rank_graph_results(
                self._store.graph_traversal(
                    seed_chunk_ids=seed_ids,
                    limit=settings.NEO4J_GRAPH_TRAVERSAL_LIMIT,
                    as_of=as_of,
                )
            )

        ranked_lists: List[List[Document]] = []
        weights: List[float] = []
        for enabled, results, weight in (
            (not disable_dense, vector_results, settings.NEO4J_VECTOR_WEIGHT),
            (not disable_sparse, fts_results, settings.NEO4J_FTS_WEIGHT),
            (graph_enabled, graph_results, settings.NEO4J_GRAPH_WEIGHT),
            (
                bool(authority_results),
                authority_results,
                settings.NEO4J_AUTHORITY_WEIGHT,
            ),
        ):
            if enabled:
                ranked_lists.append(results)
                weights.append(weight)

        candidates = self.deduplicate_results(
            self.weighted_reciprocal_rank_fusion(ranked_lists, weights)
        )
        if act_name_filter:
            candidates = self._soft_filter_act_name(candidates, act_name_filter)
        ranked = (
            candidates
            if options["disable_reranking"]
            else self.rerank_candidates(candidates, query)
        )

        results: List[Dict[str, Any]] = []
        seen_parent_ids: set[str] = set()
        seen_parent_contents: set[str] = set()

        for child in ranked:
            parent = None
            if expand_parents:
                parent_id = child.metadata.get("parent_chunk_id") or child.metadata.get(
                    "parent_id"
                )
                if parent_id:
                    if parent_id in seen_parent_ids:
                        continue
                    parent = self._store.fetch_parent(parent_id)
                    if parent:
                        parent_text = parent.page_content.strip()
                        if parent_text in seen_parent_contents:
                            continue
                        seen_parent_ids.add(parent_id)
                        seen_parent_contents.add(parent_text)

            results.append(
                {
                    "child": child,
                    "parent": parent,
                    "metadata": child.metadata,
                    "retrieval_effects": effects,
                }
            )
            if len(results) >= top_k:
                break
        logger.info("GraphRAG returned %d results for %r", len(results), query[:80])
        return results

    @staticmethod
    def describe_ablation_effects(config: dict | None = None) -> dict:
        return describe_neo4j_effects(config)

    @staticmethod
    def _soft_filter_act_name(
        candidates: List[Document], filter_name: Any
    ) -> List[Document]:
        targets = (
            [str(value).casefold().strip() for value in filter_name if value]
            if isinstance(filter_name, list)
            else [str(filter_name).casefold().strip()]
        )
        matched: List[Document] = []
        others: List[Document] = []
        for document in candidates:
            title = str(document.metadata.get("title") or "").casefold()
            (matched if any(target in title for target in targets) else others).append(
                document
            )
        return matched + others


_instance: Optional[Neo4jRetrievalService] = None


def get_neo4j_retrieval_service() -> Neo4jRetrievalService:
    global _instance
    if _instance is None:
        _instance = Neo4jRetrievalService()
    return _instance
