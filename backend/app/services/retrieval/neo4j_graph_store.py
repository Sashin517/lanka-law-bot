"""Neo4j retrieval adapter for the legal-corpus graph contract."""

from __future__ import annotations

from datetime import date, datetime
import logging
import math
import re
import unicodedata
from typing import Any, List, Optional

from langchain_core.documents import Document
from neo4j import Driver

from app.core.config import settings
from app.services.retrieval.neo4j_queries import (
    AMENDMENT_RELATIONSHIP_TYPES,
    CASE_RELATIONSHIP_TYPES,
    CHUNK_PROJECTION,
    CONCEPT_RELATIONSHIP_TYPES,
    GRAPH_TRAVERSAL_QUERY,
)

logger = logging.getLogger(__name__)


class Neo4jRetrievalError(RuntimeError):
    """Raised when Neo4j is unavailable or a retrieval query fails."""


def _as_of_value(value: date | datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    try:
        return date.fromisoformat(str(value)).isoformat()
    except ValueError as exc:
        raise ValueError("as_of must be an ISO date (YYYY-MM-DD)") from exc


def _normalize_title(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.sub(r"[^\w]+", " ", value).split())


def _smart_lucene_query(value: str) -> str:
    """Sanitize user text for Neo4j Lucene FTS while preserving legal section numbers and terms.

    Strips Lucene syntax control operators (e.g. +, -, !, (), {}, [], ^, ", ~, *, ?, :, \\, /, &, |)
    and combines substantive terms into a clean Lucene query.
    """
    if not value or not value.strip():
        return ""
    cleaned = re.sub(r'[+\-!(){}\[\]^"~*?:\\/&|]', " ", value)
    terms = [
        term
        for term in cleaned.split()
        if term and term.lower() not in {"and", "or", "not"}
    ]
    if not terms:
        return ""
    return " ".join(terms).strip()


def _lucene_escape(value: str) -> str:
    """Escape user text for Neo4j/Lucene query syntax."""
    return _smart_lucene_query(value)


CURRENT_OR_AS_OF_FILTER = """
AND (
    ($as_of IS NULL AND chunk.is_current = true)
    OR
    ($as_of IS NOT NULL AND chunk.is_current = true)
)
"""


class Neo4jGraphStore:
    """Runs vector, lexical, authority, and graph retrieval against Neo4j."""

    def __init__(self, driver: Driver) -> None:
        self._driver = driver
        self._db = settings.NEO4J_DATABASE

    @staticmethod
    def _record_to_document(record: Any) -> Document:
        node = record["chunk"]
        properties = dict(node)
        text = properties.pop("text", "") or ""
        score = float(record.get("score", 0.0) or 0.0)
        paths = record.get("graph_paths")
        metadata = {
            **properties,
            "relevance_score": score,
            "source": properties.get("source_filename", "unknown"),
        }
        if paths:
            metadata["graph_paths"] = list(paths)
        return Document(page_content=text, metadata=metadata)

    @staticmethod
    def _validate_embedding(query_embedding: List[float]) -> None:
        expected = settings.NEO4J_EMBEDDING_DIMENSION
        if len(query_embedding) != expected:
            raise ValueError(
                f"query embedding dimension {len(query_embedding)} != {expected}"
            )
        if not query_embedding or not all(
            math.isfinite(float(x)) for x in query_embedding
        ):
            raise ValueError("query embedding contains non-finite values")
        if not any(float(x) != 0.0 for x in query_embedding):
            raise ValueError("query embedding is an all-zero vector")

    def vector_search(
        self,
        query_embedding: List[float],
        top_k: int = 30,
        year_filter: Optional[int] = None,
        source_type_filter: Optional[str] = None,
        as_of: date | datetime | str | None = None,
    ) -> List[Document]:
        """Perform dense search, over-fetching before metadata filters."""
        self._validate_embedding(query_embedding)
        candidate_k = max(top_k, top_k * settings.NEO4J_FILTER_OVERFETCH_FACTOR)
        query = f"""
        CALL db.index.vector.queryNodes("chunk_embedding", $candidate_k, $query_embedding)
        YIELD node AS chunk, score
        WHERE chunk.chunk_type = 'child'
          AND ($year_filter IS NULL OR chunk.year = $year_filter)
          AND ($source_type_filter IS NULL OR chunk.source_type = $source_type_filter)
          {CURRENT_OR_AS_OF_FILTER}
        RETURN {CHUNK_PROJECTION} AS chunk, score
        ORDER BY score DESC
        LIMIT $top_k
        """
        try:
            with self._driver.session(database=self._db) as session:
                result = session.run(
                    query,
                    candidate_k=candidate_k,
                    top_k=top_k,
                    query_embedding=query_embedding,
                    year_filter=year_filter,
                    source_type_filter=source_type_filter,
                    as_of=_as_of_value(as_of),
                )
                return [self._record_to_document(rec) for rec in result]
        except (ValueError, TypeError):
            raise
        except Exception as exc:
            logger.exception("Neo4j vector search failed")
            raise Neo4jRetrievalError("Neo4j vector search failed") from exc

    def fulltext_search(
        self,
        query_text: str,
        top_k: int = 30,
        year_filter: Optional[int] = None,
        source_type_filter: Optional[str] = None,
        as_of: date | datetime | str | None = None,
    ) -> List[Document]:
        """Perform escaped lexical search with pre-filter over-fetching."""
        escaped = _lucene_escape(query_text)
        if not escaped:
            return []
        candidate_k = max(top_k, top_k * settings.NEO4J_FILTER_OVERFETCH_FACTOR)
        query = f"""
        CALL db.index.fulltext.queryNodes(
            $index_name, $query_text, {{limit: $candidate_k}}
        ) YIELD node AS chunk, score
        WHERE chunk.chunk_type = 'child'
          AND ($year_filter IS NULL OR chunk.year = $year_filter)
          AND ($source_type_filter IS NULL OR chunk.source_type = $source_type_filter)
          {CURRENT_OR_AS_OF_FILTER}
        RETURN {CHUNK_PROJECTION} AS chunk, score
        ORDER BY score DESC
        LIMIT $top_k
        """
        try:
            with self._driver.session(database=self._db) as session:
                result = session.run(
                    query,
                    index_name=settings.NEO4J_FULLTEXT_INDEX_NAME,
                    query_text=escaped,
                    candidate_k=candidate_k,
                    year_filter=year_filter,
                    source_type_filter=source_type_filter,
                    as_of=_as_of_value(as_of),
                    top_k=top_k,
                )
                return [self._record_to_document(rec) for rec in result]
        except (ValueError, TypeError):
            raise
        except Exception as exc:
            logger.exception("Neo4j full-text search failed")
            raise Neo4jRetrievalError("Neo4j full-text search failed") from exc

    def authority_search(
        self,
        authority_title: str,
        top_k: int = 20,
        as_of: date | datetime | str | None = None,
    ) -> List[Document]:
        """Resolve an Act/case title exactly first, then via the work FTS index."""
        normalized = _normalize_title(authority_title)
        escaped = _lucene_escape(authority_title)
        if not normalized:
            return []
        query = f"""
        MATCH (root)
        WHERE (root:Act OR root:CaseLaw)
          AND (toLower(root.title) CONTAINS toLower($query_text) 
               OR toLower(root.case_name) CONTAINS toLower($query_text))
        OPTIONAL MATCH (root:Act)-[:HAS_SECTION]->(:Section)-[:HAS_CHUNK]->(chunk_a:Chunk)
        OPTIONAL MATCH (root:CaseLaw)-[:HAS_CHUNK]->(chunk_c:Chunk)
        WITH coalesce(chunk_a, chunk_c) AS chunk
        WHERE chunk IS NOT NULL AND chunk.chunk_type = 'child'
          AND (
              ($as_of IS NULL AND chunk.is_current = true)
              OR
              ($as_of IS NOT NULL AND chunk.is_current = true)
          )
        RETURN {CHUNK_PROJECTION} AS chunk, 1.0 AS score
        LIMIT $top_k
        """
        try:
            with self._driver.session(database=self._db) as session:
                result = session.run(
                    query,
                    query_text=authority_title,
                    as_of=_as_of_value(as_of),
                    top_k=top_k,
                )
                return [self._record_to_document(rec) for rec in result]
        except (ValueError, TypeError):
            raise
        except Exception as exc:
            logger.exception("Neo4j authority search failed")
            raise Neo4jRetrievalError("Neo4j authority search failed") from exc

    def graph_traversal(
        self,
        seed_chunk_ids: List[str],
        limit: int = 15,
        as_of: date | datetime | str | None = None,
    ) -> List[Document]:
        """Expand canonical assertions plus compatibility graph relationships."""
        seed_chunk_ids = list(dict.fromkeys(seed_chunk_ids))
        if not seed_chunk_ids:
            return []
        try:
            with self._driver.session(database=self._db) as session:
                result = session.run(
                    GRAPH_TRAVERSAL_QUERY,
                    seed_chunk_ids=seed_chunk_ids,
                    limit=limit,
                    as_of=_as_of_value(as_of),
                    amendment_relationship_types=AMENDMENT_RELATIONSHIP_TYPES,
                    case_relationship_types=CASE_RELATIONSHIP_TYPES,
                    concept_relationship_types=CONCEPT_RELATIONSHIP_TYPES,
                )
                return [self._record_to_document(rec) for rec in result]
        except (ValueError, TypeError):
            raise
        except Exception as exc:
            logger.exception("Neo4j graph traversal failed")
            raise Neo4jRetrievalError("Neo4j graph traversal failed") from exc

    def fetch_parent(self, parent_chunk_id: str) -> Optional[Document]:
        query = f"""
        MATCH (chunk:Chunk {{chunk_id: $parent_id, chunk_type: 'parent'}})
        RETURN {CHUNK_PROJECTION} AS chunk
        LIMIT 1
        """
        try:
            with self._driver.session(database=self._db) as session:
                record = session.run(query, parent_id=parent_chunk_id).single()
                return self._record_to_document(record) if record else None
        except Exception as exc:
            logger.exception("Neo4j parent expansion failed")
            raise Neo4jRetrievalError("Neo4j parent expansion failed") from exc
