"""Validate/create the Neo4j schema used by the Colab legal-corpus ingester.

The default ``validate`` mode never drops an index. To recreate an incompatible
semantic index, set NEO4J_INDEX_MIGRATION_MODE=recreate only after taking and
restore-testing a backup, then also set NEO4J_BACKUP_CONFIRMED=true and
NEO4J_BACKUP_REFERENCE to the immutable snapshot/dump identifier.
"""
from __future__ import annotations

import logging
import os
import re
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from neo4j import GraphDatabase

from app.core.config import settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)


CONSTRAINTS = [
    "CREATE CONSTRAINT legal_work_id IF NOT EXISTS FOR (n:LegalWork) REQUIRE n.work_id IS UNIQUE",
    "CREATE CONSTRAINT expression_id IF NOT EXISTS FOR (n:LegalExpression) REQUIRE n.expression_id IS UNIQUE",
    "CREATE CONSTRAINT source_id IF NOT EXISTS FOR (n:SourceFile) REQUIRE n.source_id IS UNIQUE",
    "CREATE CONSTRAINT provision_id IF NOT EXISTS FOR (n:Provision) REQUIRE n.provision_id IS UNIQUE",
    "CREATE CONSTRAINT chunk_id IF NOT EXISTS FOR (n:Chunk) REQUIRE n.chunk_id IS UNIQUE",
    "CREATE CONSTRAINT assertion_id IF NOT EXISTS FOR (n:GroundedAssertion) REQUIRE n.assertion_id IS UNIQUE",
    "CREATE CONSTRAINT candidate_id IF NOT EXISTS FOR (n:AuthorityCandidate) REQUIRE n.candidate_id IS UNIQUE",
    "CREATE CONSTRAINT run_id IF NOT EXISTS FOR (n:IngestionRun) REQUIRE n.run_id IS UNIQUE",
    "CREATE CONSTRAINT concept_id IF NOT EXISTS FOR (n:LegalConcept) REQUIRE n.concept_id IS UNIQUE",
    "CREATE CONSTRAINT court_id IF NOT EXISTS FOR (n:Court) REQUIRE n.court_id IS UNIQUE",
    "CREATE CONSTRAINT judge_id IF NOT EXISTS FOR (n:Judge) REQUIRE n.judge_id IS UNIQUE",
    "CREATE CONSTRAINT party_id IF NOT EXISTS FOR (n:Party) REQUIRE n.party_id IS UNIQUE",
    "CREATE CONSTRAINT lock_id IF NOT EXISTS FOR (n:IngestionLock) REQUIRE n.lock_id IS UNIQUE",
]

PROPERTY_INDEXES = [
    "CREATE INDEX work_title IF NOT EXISTS FOR (n:LegalWork) ON (n.normalized_title)",
    "CREATE INDEX expression_active IF NOT EXISTS FOR (n:LegalExpression) ON (n.is_active)",
    "CREATE INDEX expression_validity IF NOT EXISTS FOR (n:LegalExpression) ON (n.valid_from, n.valid_to)",
    "CREATE INDEX provision_number IF NOT EXISTS FOR (n:Provision) ON (n.normalized_number)",
    "CREATE INDEX chunk_current IF NOT EXISTS FOR (n:Chunk) ON (n.is_current)",
    "CREATE INDEX chunk_work IF NOT EXISTS FOR (n:Chunk) ON (n.work_id)",
    "CREATE INDEX candidate_status IF NOT EXISTS FOR (n:AuthorityCandidate) ON (n.resolution_status)",
    "CREATE INDEX assertion_expression IF NOT EXISTS FOR (n:GroundedAssertion) ON (n.expression_id)",
]


def _index(session: Any, name: str) -> Any:
    return session.run(
        "SHOW INDEXES YIELD name,type,properties,options "
        "WHERE name=$name RETURN type,properties,options",
        name=name,
    ).single()


def _allow_recreate() -> bool:
    mode = settings.NEO4J_INDEX_MIGRATION_MODE.casefold()
    if mode not in {"validate", "recreate"}:
        raise RuntimeError("NEO4J_INDEX_MIGRATION_MODE must be validate or recreate")
    if mode == "recreate" and (
        not settings.NEO4J_BACKUP_CONFIRMED
        or not settings.NEO4J_BACKUP_REFERENCE.strip()
    ):
        raise RuntimeError(
            "recreate mode requires a restore-tested backup and a non-empty "
            "NEO4J_BACKUP_REFERENCE"
        )
    return mode == "recreate"


def _semantic_indexes(session: Any, recreate: bool) -> None:
    for name in (
        settings.NEO4J_VECTOR_INDEX_NAME,
        settings.NEO4J_FULLTEXT_INDEX_NAME,
        settings.NEO4J_WORK_FULLTEXT_INDEX_NAME,
    ):
        if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
            raise RuntimeError(f"unsafe Neo4j index name: {name!r}")
    vector = _index(session, settings.NEO4J_VECTOR_INDEX_NAME)
    if vector:
        config = (vector["options"] or {}).get("indexConfig", {})
        dimensions = config.get("vector.dimensions") or config.get("`vector.dimensions`")
        incompatible = (
            vector["type"] != "VECTOR"
            or vector["properties"] != ["embedding"]
            or int(dimensions or 0) != settings.NEO4J_EMBEDDING_DIMENSION
        )
        if incompatible and not recreate:
            raise RuntimeError("chunk vector index is incompatible; no changes made")
        if incompatible:
            session.run(f"DROP INDEX `{settings.NEO4J_VECTOR_INDEX_NAME}`").consume()
            vector = None
    if not vector:
        session.run(
            f"""CREATE VECTOR INDEX `{settings.NEO4J_VECTOR_INDEX_NAME}`
            FOR (n:Chunk) ON (n.embedding)
            OPTIONS {{indexConfig: {{`vector.dimensions`: $dimensions,
            `vector.similarity_function`: 'cosine'}}}}""",
            dimensions=settings.NEO4J_EMBEDDING_DIMENSION,
        ).consume()

    expected = {"text", "title", "source_filename", "breadcrumb"}
    fulltext = _index(session, settings.NEO4J_FULLTEXT_INDEX_NAME)
    incompatible = bool(
        fulltext
        and (
            fulltext["type"] != "FULLTEXT"
            or set(fulltext["properties"] or []) != expected
        )
    )
    if incompatible and not recreate:
        raise RuntimeError("chunk full-text index is incompatible; no changes made")
    if incompatible:
        session.run(f"DROP INDEX `{settings.NEO4J_FULLTEXT_INDEX_NAME}`").consume()
        fulltext = None
    if not fulltext:
        session.run(
            f"CREATE FULLTEXT INDEX `{settings.NEO4J_FULLTEXT_INDEX_NAME}` "
            "FOR (n:Chunk) ON EACH [n.text,n.title,n.source_filename,n.breadcrumb]"
        ).consume()

    session.run(
        f"CREATE FULLTEXT INDEX `{settings.NEO4J_WORK_FULLTEXT_INDEX_NAME}` "
        "IF NOT EXISTS FOR (n:LegalWork) "
        "ON EACH [n.title,n.case_name,n.reporter_citation]"
    ).consume()


def setup_schema() -> None:
    recreate = _allow_recreate()
    driver = GraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
    )
    try:
        driver.verify_connectivity()
        with driver.session(database=settings.NEO4J_DATABASE) as session:
            for statement in [*CONSTRAINTS, *PROPERTY_INDEXES]:
                session.run(statement).consume()
            _semantic_indexes(session, recreate)
            session.run("CALL db.awaitIndexes(300)").consume()
            offline = list(
                session.run(
                    "SHOW INDEXES YIELD name,state WHERE state <> 'ONLINE' "
                    "RETURN name,state"
                )
            )
            if offline:
                raise RuntimeError(f"Neo4j indexes are not ONLINE: {offline}")
            session.run(
                "MERGE (s:SchemaVersion {component:'legal-corpus'}) "
                "SET s.version='2.1.0',s.applied_at=datetime(),"
                "s.index_migration_mode=$mode,s.backup_reference=$backup",
                mode=settings.NEO4J_INDEX_MIGRATION_MODE,
                backup=settings.NEO4J_BACKUP_REFERENCE or None,
            ).consume()
        logger.info("Canonical Neo4j schema is ready")
    finally:
        driver.close()


if __name__ == "__main__":
    setup_schema()
