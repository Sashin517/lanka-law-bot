from __future__ import annotations

import os
from collections.abc import Generator

from sqlalchemy import Connection, create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


os.makedirs(os.path.dirname(settings.METADATA_DB_PATH), exist_ok=True)

engine = create_engine(
    f"sqlite:///{settings.METADATA_DB_PATH}",
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def init_db() -> None:
    from app.models import document  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _apply_sqlite_compat_migrations()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _apply_sqlite_compat_migrations() -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    if "document_chunks" in tables:
        columns = {column["name"] for column in inspector.get_columns("document_chunks")}
        if "qdrant_point_id" in columns:
            with engine.begin() as conn:
                _rebuild_document_chunks_table(conn, columns)
        elif "vector_record_id" not in columns:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE document_chunks "
                        "ADD COLUMN vector_record_id VARCHAR(64)"
                    )
                )


def _rebuild_document_chunks_table(conn: Connection, columns: set[str]) -> None:
    select_vector_record_id = (
        "COALESCE(vector_record_id, qdrant_point_id)"
        if "vector_record_id" in columns
        else "qdrant_point_id"
    )
    select_page_start = "page_start" if "page_start" in columns else "NULL"
    select_page_end = "page_end" if "page_end" in columns else "NULL"
    select_heading_path = "heading_path" if "heading_path" in columns else "NULL"
    select_clause_label = "clause_label" if "clause_label" in columns else "NULL"

    conn.execute(text("PRAGMA foreign_keys=OFF"))
    conn.execute(text("ALTER TABLE document_chunks RENAME TO document_chunks_legacy"))
    conn.execute(
        text(
            """
            CREATE TABLE document_chunks (
                id VARCHAR(128) NOT NULL PRIMARY KEY,
                document_id VARCHAR(64) NOT NULL,
                parent_id VARCHAR(128),
                chunk_type VARCHAR(64) NOT NULL,
                chunk_strategy VARCHAR(128) NOT NULL,
                vector_record_id VARCHAR(64) NOT NULL,
                page_start INTEGER,
                page_end INTEGER,
                heading_path TEXT,
                clause_label VARCHAR(255),
                text_hash VARCHAR(64) NOT NULL,
                FOREIGN KEY(document_id) REFERENCES user_documents (id) ON DELETE CASCADE
            )
            """
        )
    )
    conn.execute(
        text(
            f"""
            INSERT INTO document_chunks (
                id,
                document_id,
                parent_id,
                chunk_type,
                chunk_strategy,
                vector_record_id,
                page_start,
                page_end,
                heading_path,
                clause_label,
                text_hash
            )
            SELECT
                id,
                document_id,
                parent_id,
                chunk_type,
                chunk_strategy,
                {select_vector_record_id},
                {select_page_start},
                {select_page_end},
                {select_heading_path},
                {select_clause_label},
                text_hash
            FROM document_chunks_legacy
            """
        )
    )
    conn.execute(text("DROP TABLE document_chunks_legacy"))
    conn.execute(text("CREATE INDEX ix_document_chunks_document_id ON document_chunks (document_id)"))
    conn.execute(text("CREATE INDEX ix_document_chunks_parent_id ON document_chunks (parent_id)"))
    conn.execute(text("CREATE INDEX ix_document_chunks_chunk_type ON document_chunks (chunk_type)"))
    conn.execute(text("CREATE INDEX ix_document_chunks_vector_record_id ON document_chunks (vector_record_id)"))
    conn.execute(text("CREATE INDEX ix_document_chunks_text_hash ON document_chunks (text_hash)"))
    conn.execute(text("PRAGMA foreign_keys=ON"))
