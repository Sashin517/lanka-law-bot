"""
Setup Neo4j schema: constraints, property indexes, vector index, and full-text indexes.

Run this script ONCE after starting the Neo4j Docker container to prepare the database
for the LankaLawBot GraphRAG ingestion pipeline.

Usage:
    python scripts/setup_neo4j_schema.py
"""
from __future__ import annotations

import logging
import sys
import os

# Allow imports from the backend package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from neo4j import GraphDatabase

from app.core.config import settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cypher statements executed in order
# ---------------------------------------------------------------------------

CONSTRAINTS = [
    "CREATE CONSTRAINT act_id IF NOT EXISTS FOR (a:Act) REQUIRE a.act_id IS UNIQUE",
    "CREATE CONSTRAINT section_id IF NOT EXISTS FOR (s:Section) REQUIRE s.section_id IS UNIQUE",
    "CREATE CONSTRAINT chunk_id IF NOT EXISTS FOR (c:Chunk) REQUIRE c.chunk_id IS UNIQUE",
    "CREATE CONSTRAINT case_id IF NOT EXISTS FOR (cl:CaseLaw) REQUIRE cl.case_id IS UNIQUE",
    "CREATE CONSTRAINT concept_id IF NOT EXISTS FOR (lc:LegalConcept) REQUIRE lc.concept_id IS UNIQUE",
    "CREATE CONSTRAINT court_name IF NOT EXISTS FOR (ct:Court) REQUIRE ct.name IS UNIQUE",
    "CREATE CONSTRAINT judge_name IF NOT EXISTS FOR (j:Judge) REQUIRE j.name IS UNIQUE",
]

PROPERTY_INDEXES = [
    "CREATE INDEX chunk_year IF NOT EXISTS FOR (c:Chunk) ON (c.year)",
    "CREATE INDEX chunk_source_type IF NOT EXISTS FOR (c:Chunk) ON (c.source_type)",
    "CREATE INDEX chunk_type IF NOT EXISTS FOR (c:Chunk) ON (c.chunk_type)",
    "CREATE INDEX chunk_title IF NOT EXISTS FOR (c:Chunk) ON (c.title)",
    "CREATE INDEX chunk_is_current IF NOT EXISTS FOR (c:Chunk) ON (c.is_current)",
    "CREATE INDEX section_act IF NOT EXISTS FOR (s:Section) ON (s.act_id)",
]

VECTOR_INDEX = """
CREATE VECTOR INDEX `chunk-embeddings` IF NOT EXISTS
FOR (c:Chunk) ON (c.embedding)
OPTIONS {indexConfig: {
    `vector.dimensions`: $dimensions,
    `vector.similarity_function`: 'cosine'
}}
"""

FULLTEXT_INDEXES = [
    "CREATE FULLTEXT INDEX `chunk-fulltext` IF NOT EXISTS FOR (c:Chunk) ON EACH [c.text]",
    "CREATE FULLTEXT INDEX `act-fulltext` IF NOT EXISTS FOR (a:Act) ON EACH [a.title, a.short_title]",
    "CREATE FULLTEXT INDEX `case-fulltext` IF NOT EXISTS FOR (cl:CaseLaw) ON EACH [cl.case_name]",
]


def setup_schema() -> None:
    """Connect to Neo4j and execute all schema DDL statements."""

    logger.info(
        "Connecting to Neo4j at %s as user '%s' ...",
        settings.NEO4J_URI,
        settings.NEO4J_USER,
    )
    driver = GraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
    )

    try:
        driver.verify_connectivity()
        logger.info("Connected to Neo4j successfully.")
    except Exception as exc:
        logger.error("Cannot connect to Neo4j: %s", exc)
        logger.error(
            "Make sure Neo4j is running: "
            "docker compose -f docker-compose.neo4j.yml up -d"
        )
        sys.exit(1)

    with driver.session(database=settings.NEO4J_DATABASE) as session:
        # 1. Uniqueness constraints
        for stmt in CONSTRAINTS:
            logger.info("  constraint  → %s", stmt.split("FOR")[0].strip())
            session.run(stmt)

        # 2. Property indexes
        for stmt in PROPERTY_INDEXES:
            logger.info("  index       → %s", stmt.split("FOR")[0].strip())
            session.run(stmt)

        # 3. Vector index
        logger.info(
            "  vector idx  → chunk-embeddings (%d dimensions, cosine)",
            settings.NEO4J_EMBEDDING_DIMENSION,
        )
        session.run(
            VECTOR_INDEX,
            dimensions=settings.NEO4J_EMBEDDING_DIMENSION,
        )

        # 4. Full-text indexes
        for stmt in FULLTEXT_INDEXES:
            idx_name = stmt.split("`")[1]
            logger.info("  fulltext    → %s", idx_name)
            session.run(stmt)

    # 5. Verify
    with driver.session(database=settings.NEO4J_DATABASE) as session:
        result = session.run("SHOW INDEXES YIELD name, type, state")
        records = list(result)
        logger.info("\n--- Indexes Created (%d total) ---", len(records))
        for rec in records:
            logger.info(
                "  %-30s  type=%-12s  state=%s",
                rec["name"],
                rec["type"],
                rec["state"],
            )

    driver.close()
    logger.info("\nSchema setup complete.")


if __name__ == "__main__":
    setup_schema()
