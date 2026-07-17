"""
Neo4j Graph Store wrapper.
Handles raw Cypher queries for vector search, full-text search, and graph traversal.
Converts Neo4j node structures into LangChain Document formats.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from langchain_core.documents import Document
from neo4j import Driver, GraphDatabase

from app.core.config import settings

logger = logging.getLogger(__name__)


class Neo4jGraphStore:
    """Wrapper around Neo4j driver for execution of retrieval Cypher queries."""

    def __init__(self, driver: Driver) -> None:
        self._driver = driver
        self._db = settings.NEO4J_DATABASE

    def _node_to_document(self, record: Any) -> Document:
        """Converts a Neo4j Chunk node record to a LangChain Document."""
        node = record["chunk"]
        score = record.get("score", 0.0)

        # Extract properties
        properties = dict(node)
        text = properties.pop("text", "") or ""

        # Build metadata dictionary
        metadata = {
            **properties,
            "relevance_score": score,
            "source": properties.get("source_filename", "unknown"),
        }
        return Document(page_content=text, metadata=metadata)

    def vector_search(
        self,
        query_embedding: List[float],
        top_k: int = 30,
        year_filter: Optional[int] = None,
        source_type_filter: Optional[str] = None,
    ) -> List[Document]:
        """Perform dense semantic search on the vector index."""
        query = """
        CALL db.index.vector.queryNodes($index_name, $top_k, $query_embedding)
        YIELD node AS chunk, score
        WHERE chunk.chunk_type IN ['child', 'section_summary']
          AND chunk.is_current = true
          AND ($year_filter IS NULL OR chunk.year = $year_filter)
          AND ($source_type_filter IS NULL OR chunk.source_type = $source_type_filter)
        RETURN chunk, score
        ORDER BY score DESC
        LIMIT $top_k
        """
        try:
            with self._driver.session(database=self._db) as session:
                result = session.run(
                    query,
                    index_name=settings.NEO4J_VECTOR_INDEX_NAME,
                    top_k=top_k,
                    query_embedding=query_embedding,
                    year_filter=year_filter,
                    source_type_filter=source_type_filter,
                )
                return [self._node_to_document(rec) for rec in result]
        except Exception as exc:
            logger.exception("Neo4j vector search failed: %s", exc)
            return []

    def fulltext_search(
        self,
        query_text: str,
        top_k: int = 30,
        year_filter: Optional[int] = None,
    ) -> List[Document]:
        """Perform lexical FTS on the Lucene index."""
        query = """
        CALL db.index.fulltext.queryNodes($index_name, $query_text)
        YIELD node AS chunk, score
        WHERE chunk.chunk_type IN ['child', 'section_summary']
          AND chunk.is_current = true
          AND ($year_filter IS NULL OR chunk.year = $year_filter)
        RETURN chunk, score
        ORDER BY score DESC
        LIMIT $top_k
        """
        try:
            with self._driver.session(database=self._db) as session:
                result = session.run(
                    query,
                    index_name=settings.NEO4J_FULLTEXT_INDEX_NAME,
                    query_text=query_text,
                    year_filter=year_filter,
                    top_k=top_k,
                )
                return [self._node_to_document(rec) for rec in result]
        except Exception as exc:
            logger.exception("Neo4j full-text search failed: %s", exc)
            return []

    def graph_traversal(
        self,
        seed_chunk_ids: List[str],
        limit: int = 15,
    ) -> List[Document]:
        """Retrieve chunks from graph paths: related Acts, citing cases, and concept links."""
        if not seed_chunk_ids:
            return []

        query = """
        UNWIND $seed_chunk_ids AS seed_id
        MATCH (seed:Chunk {chunk_id: seed_id})
        
        // Strategy 1: Expand to parent Acts & Sections, then traverse amendments and repeals
        OPTIONAL MATCH (seed)<-[:HAS_CHUNK]-(s:Section)<-[:HAS_SECTION]-(a:Act)
        OPTIONAL MATCH (a)-[:AMENDS|REPEALS]->(related_act:Act)-[:HAS_SECTION]->(related_s:Section)-[:HAS_CHUNK]->(related_c:Chunk)
        
        // Strategy 2: Case law that cites/interprets the seed section
        OPTIONAL MATCH (case:CaseLaw)-[:CITES_STATUTE|INTERPRETS]->(s)
        OPTIONAL MATCH (case)-[:HAS_CHUNK]->(case_c:Chunk)
        
        // Strategy 3: Concept-based expansion
        OPTIONAL MATCH (s)-[:RELATES_TO]->(concept:LegalConcept)<-[:RELATES_TO]-(other_s:Section)
        OPTIONAL MATCH (other_s)-[:HAS_CHUNK]->(concept_c:Chunk)
        
        WITH collect(DISTINCT related_c) + collect(DISTINCT case_c) + collect(DISTINCT concept_c) AS combined
        UNWIND combined AS chunk
        WITH DISTINCT chunk
        WHERE chunk IS NOT NULL 
          AND chunk.chunk_type IN ['child', 'section_summary']
          AND chunk.is_current = true
        RETURN chunk
        LIMIT $limit
        """
        try:
            with self._driver.session(database=self._db) as session:
                result = session.run(
                    query,
                    seed_chunk_ids=seed_chunk_ids,
                    limit=limit,
                )
                # Since graph traversal query returns raw nodes without score, convert with default score
                return [
                    self._node_to_document({"chunk": rec["chunk"], "score": 0.5})
                    for rec in result
                ]
        except Exception as exc:
            logger.exception("Neo4j graph traversal search failed: %s", exc)
            return []

    def fetch_parent(self, parent_chunk_id: str) -> Optional[Document]:
        """Fetch parent chunk node by its unique chunk_id."""
        query = """
        MATCH (c:Chunk {chunk_id: $parent_id, chunk_type: 'parent'})
        RETURN c AS chunk
        LIMIT 1
        """
        try:
            with self._driver.session(database=self._db) as session:
                result = session.run(query, parent_id=parent_chunk_id)
                rec = result.single()
                if rec:
                    return self._node_to_document({"chunk": rec["chunk"]})
                return None
        except Exception as exc:
            logger.exception("Neo4j fetch parent failed: %s", exc)
            return None
