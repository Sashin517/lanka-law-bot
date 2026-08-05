from __future__ import annotations

import logging
from threading import Lock
from typing import Any

from langchain_core.documents import Document
from app.core.config import settings
from app.services.retrieval.legal_vector_store import (
    LegalVectorStore,
    PineconeLegalBM25Retriever,
    PineconeLegalHybridRetriever,
    PineconeLegalRetriever,
)
from evaluation.ablation import (
    AblationConfigurationError,
    describe_pinecone_effects,
    retrieval_search_kwargs,
)

logger = logging.getLogger(__name__)


class RetrievalService:
    """
    Hybrid retrieval pipeline (Pinecone-backed):

    1. Dense search  (one Pinecone document index, children only)
    2. Lexical search (multi-field BM25 on the same documents)
    3. Reciprocal Rank Fusion  (merge + deduplicate)
    4. Cross-Encoder Re-Ranking (precision scoring)
    5. Parent chunk expansion  (from Pinecone by chunk_id)
    """

    def __init__(self) -> None:
        logger.info("Initialising RetrievalService ...")

        self._legal_store = LegalVectorStore()

        # --- Dense retriever ---
        self._dense_retriever = PineconeLegalRetriever(
            store=self._legal_store, k=settings.RETRIEVAL_CANDIDATES_K
        )

        self._bm25_retriever = PineconeLegalBM25Retriever(
            store=self._legal_store,
            k=settings.RETRIEVAL_CANDIDATES_K,
        )
        self._hybrid_retriever = PineconeLegalHybridRetriever(
            store=self._legal_store,
            k=settings.RETRIEVAL_CANDIDATES_K,
            dense_weight=settings.DENSE_WEIGHT,
            sparse_weight=settings.SPARSE_WEIGHT,
        )
        logger.info("Single-index Pinecone dense + BM25 retrieval enabled.")

        # Avoid model downloads and heavyweight initialisation during imports,
        # worker startup, health checks, and BM25/dense-only ablations.
        self._reranker = None
        self._reranker_lock = Lock()

        logger.info("RetrievalService ready.")

    def search(
        self,
        query: str,
        top_k: int = 10,
        expand_parents: bool = True,
        year_filter: list[int] | int | None = None,
        act_name_filter: list[str] | str | None = None,
        **kwargs,
    ) -> list[dict]:
        """
        Execute hybrid search -> re-rank -> deduplicate -> parent expansion.

        Parameters
        ----------
        year_filter : int | list[int] | None
            Restrict retrieval to chunks whose ``year`` metadata matches.
        act_name_filter : str | list[str] | None
            Restrict retrieval using full-text matching against ``title``.

        Returns a list of dicts, each containing:
            - ``child``    : Document  - the matched child chunk
            - ``parent``   : Document | None - expanded parent context
            - ``metadata`` : dict - full structured metadata
        """
        requested = {
            **kwargs,
            "expand_parents": expand_parents,
        }
        effects = self.describe_ablation_effects(requested)
        options = retrieval_search_kwargs(requested)
        disable_bm25 = options["disable_bm25"]
        disable_dense = options["disable_dense"]
        disable_reranking = options["disable_reranking"]

        y_filters = [year_filter] if isinstance(year_filter, int) else year_filter
        a_filters = (
            [act_name_filter] if isinstance(act_name_filter, str) else act_name_filter
        )
        pinecone_filter = self._build_pinecone_filter(y_filters, a_filters)

        # Retriever instances are immutable request descriptions.  Construct
        # filtered variants per request instead of mutating shared singleton
        # state, which would leak filters between concurrent API requests.
        dense_retriever = self._dense_retriever
        bm25_retriever = self._bm25_retriever
        hybrid_retriever = self._hybrid_retriever
        if pinecone_filter:
            dense_retriever = PineconeLegalRetriever(
                store=self._legal_store,
                k=settings.RETRIEVAL_CANDIDATES_K,
                metadata_filters=pinecone_filter,
            )
            bm25_retriever = PineconeLegalBM25Retriever(
                store=self._legal_store,
                k=settings.RETRIEVAL_CANDIDATES_K,
                metadata_filters=pinecone_filter,
            )
            hybrid_retriever = PineconeLegalHybridRetriever(
                store=self._legal_store,
                k=settings.RETRIEVAL_CANDIDATES_K,
                dense_weight=settings.DENSE_WEIGHT,
                sparse_weight=settings.SPARSE_WEIGHT,
                metadata_filters=pinecone_filter,
            )

        # 1. Determine base retriever
        if disable_dense:
            base_retriever = bm25_retriever
        elif disable_bm25:
            base_retriever = dense_retriever
        else:
            base_retriever = hybrid_retriever or dense_retriever

        # 2. Execute retrieval
        candidates: list[Document] = []
        try:
            candidates = base_retriever.invoke(query)
        except Exception as exc:
            if disable_dense:
                raise AblationConfigurationError(
                    "Sparse-only retrieval failed; refusing to fall back to dense "
                    "because that would invalidate the ablation"
                ) from exc
            # The hybrid retriever already degrades to either healthy channel
            # and raises only when both fail. Retrying dense here duplicates a
            # known failed embedding/network call and inflates tail latency.
            logger.exception("Legal retrieval failed.")
            raise

        # 3. Optionally re-rank
        if not disable_reranking and candidates:
            try:
                candidates = self._get_reranker().compress_documents(candidates, query)
                candidates = self._prune_low_relevance(candidates)
            except Exception:
                logger.exception("Re-ranking failed. Falling back to base ranking.")

        # 4. Deduplicate by chunk_id and content fingerprint
        seen_ids: set[str] = set()
        seen_content: set[str] = set()
        unique: list[Document] = []
        for doc in candidates:
            cid = doc.metadata.get("chunk_id", "")
            content_key = doc.page_content[:500].strip()

            if cid and cid in seen_ids:
                continue
            if content_key in seen_content:
                continue

            if cid:
                seen_ids.add(cid)
            seen_content.add(content_key)
            unique.append(doc)

        # 5. Defence-in-depth metadata check (fail closed)
        if year_filter or act_name_filter:
            unique = self._post_filter_metadata(
                unique,
                y_filters,
                a_filters,
            )

        # 6. Expand to parents with deduplication
        results: list[dict] = []
        seen_parent_ids: set[str] = set()
        seen_parent_contents: set[str] = set()

        for child in unique:
            parent = None
            if expand_parents:
                parent_id = child.metadata.get("parent_id") or child.metadata.get(
                    "parent_chunk_id"
                )
                if parent_id:
                    if parent_id in seen_parent_ids:
                        continue
                    parent = self._legal_store.fetch_parent(parent_id)
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

        logger.info(
            "Retrieved %d results for query: '%s'",
            len(results),
            query[:80],
        )
        return results

    def describe_ablation_effects(self, config: dict | None = None) -> dict:
        """Validate and describe the retrieval behavior for an ablation.

        Requested component removals must change the configured pipeline.  An
        unavailable BM25 or reranker therefore fails preflight instead of
        producing a misleading comparison against an identical baseline.
        """
        return describe_pinecone_effects(
            config,
            bm25_available=self._bm25_retriever is not None,
            reranking_available=bool(settings.RERANKER_MODEL),
        )

    def _get_reranker(self):
        """Construct and cache the optional cross-encoder on first use."""
        if self._reranker is not None:
            return self._reranker

        with self._reranker_lock:
            if self._reranker is None:
                from langchain_community.cross_encoders import HuggingFaceCrossEncoder
                from langchain_classic.retrievers.document_compressors.cross_encoder_rerank import (
                    CrossEncoderReranker,
                )

                cross_encoder = HuggingFaceCrossEncoder(
                    model_name=settings.RERANKER_MODEL,
                )
                self._reranker = CrossEncoderReranker(
                    model=cross_encoder,
                    top_n=settings.RERANKER_TOP_N,
                )
        return self._reranker

    def _prune_low_relevance(self, candidates: list[Document]) -> list[Document]:
        """Drop candidates whose cross-encoder score falls below the threshold.

        If pruning would remove every result, keep the top candidate as a
        safety valve. Documents without ``relevance_score`` are always kept.
        """
        threshold = settings.RELEVANCE_SCORE_THRESHOLD
        if threshold <= 0:
            return candidates

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

        return pruned if pruned else candidates[:1]

    @staticmethod
    def _build_pinecone_filter(
        year_filters: list[int] | None,
        act_name_filters: list[str] | None,
    ) -> dict | None:
        """Translate route constraints into pre-scoring document filters."""
        clauses: list[dict] = []

        years = sorted({int(year) for year in (year_filters or [])})
        if len(years) == 1:
            clauses.append({"year": {"$eq": years[0]}})
        elif years:
            clauses.append({"year": {"$in": years}})

        titles = [
            str(value).strip()
            for value in (act_name_filters or [])
            if str(value).strip()
        ]
        title_filters: list[dict] = []
        for title in titles:
            title_filters.append({"title": {"$eq": title}})
            title_filters.append({"case_name": {"$eq": title}})
        if len(title_filters) == 1:
            clauses.append(title_filters[0])
        elif title_filters:
            clauses.append({"$or": title_filters})

        if not clauses:
            return None
        return clauses[0] if len(clauses) == 1 else {"$and": clauses}

    @staticmethod
    def _post_filter_metadata(
        candidates: list[Document],
        year_filters: list[int] | None,
        act_name_filters: list[str] | None,
    ) -> list[Document]:
        """Filter already-retrieved candidates by metadata constraints.

        This is a defence-in-depth check after Pinecone's pre-scoring filter.
        Constraints are fail-closed: missing metadata never silently broadens a
        legal query, and year/title constraints are combined with AND.
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
                    year_match = False

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
                    words = [
                        w.lower()
                        for w in re.findall(r"\b\w{4,}\b", act_name)
                        if w.lower() not in ("ordinance", "amendment")
                    ]
                    if words and all(w in title for w in words):
                        title_match = True
                        break

            if year_match and title_match:
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

        logger.debug("Metadata filter matched 0/%d candidates.", len(candidates))
        return []


_instance: RetrievalService | None = None


def get_retrieval_service() -> Any:
    """Singleton factory for RetrievalService, routing dynamically by configuration."""
    global _instance
    backend = getattr(settings, "RETRIEVAL_BACKEND", "pinecone").lower()
    if backend == "neo4j":
        from app.services.retrieval.neo4j_retrieval_service import (
            get_neo4j_retrieval_service,
        )

        return get_neo4j_retrieval_service()

    if _instance is None:
        _instance = RetrievalService()
    return _instance
