from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base


def utcnow() -> datetime:
    return datetime.utcnow()


class UserDocument(Base):
    __tablename__ = "user_documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    matter_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    filename: Mapped[str] = mapped_column(String(512))
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    stored_path: Mapped[str] = mapped_column(Text)
    markdown_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_hash: Mapped[str] = mapped_column(String(64), index=True)
    document_type: Mapped[str] = mapped_column(String(128), default="unknown")
    status: Mapped[str] = mapped_column(String(32), index=True, default="queued")
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    jobs: Mapped[list[IngestionJob]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )
    chunks: Mapped[list[DocumentChunk]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("user_documents.id", ondelete="CASCADE"),
        index=True,
    )
    status: Mapped[str] = mapped_column(String(32), index=True, default="queued")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    document: Mapped[UserDocument] = relationship(back_populates="jobs")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("user_documents.id", ondelete="CASCADE"),
        index=True,
    )
    parent_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    chunk_type: Mapped[str] = mapped_column(String(64), index=True)
    chunk_strategy: Mapped[str] = mapped_column(String(128))
    qdrant_point_id: Mapped[str] = mapped_column(String(64), index=True)
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    heading_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    clause_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    text_hash: Mapped[str] = mapped_column(String(64), index=True)

    document: Mapped[UserDocument] = relationship(back_populates="chunks")
