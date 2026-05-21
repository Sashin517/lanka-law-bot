from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base


def utcnow() -> datetime:
    return datetime.utcnow()


class DraftDocument(Base):
    __tablename__ = "draft_documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    matter_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    title: Mapped[str] = mapped_column(String(512))
    document_type: Mapped[str] = mapped_column(String(128), index=True, default="unknown")
    status: Mapped[str] = mapped_column(String(32), index=True, default="draft")
    editor_json: Mapped[str] = mapped_column(Text, default="{}")
    markdown_content: Mapped[str] = mapped_column(Text, default="")
    html_content: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(32), index=True, default="agent")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    versions: Mapped[list[DraftDocumentVersion]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DraftDocumentVersion.version_number",
    )
    changes: Mapped[list[DraftDocumentChange]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )
    context_snapshots: Mapped[list[DraftContextSnapshot]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )


class DraftDocumentVersion(Base):
    __tablename__ = "draft_document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version_number", name="uq_draft_version_number"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("draft_documents.id", ondelete="CASCADE"),
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer)
    editor_json: Mapped[str] = mapped_column(Text, default="{}")
    markdown_content: Mapped[str] = mapped_column(Text, default="")
    change_summary: Mapped[str] = mapped_column(Text, default="")
    changed_by: Mapped[str] = mapped_column(String(32), index=True)
    agent_run_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    context_snapshot_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("draft_context_snapshots.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    document: Mapped[DraftDocument] = relationship(back_populates="versions")
    context_snapshot: Mapped[DraftContextSnapshot | None] = relationship(
        back_populates="versions",
    )
    changes: Mapped[list[DraftDocumentChange]] = relationship(
        back_populates="version",
    )


class DraftDocumentChange(Base):
    __tablename__ = "draft_document_changes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("draft_documents.id", ondelete="CASCADE"),
        index=True,
    )
    version_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("draft_document_versions.id", ondelete="CASCADE"),
        index=True,
    )
    operation_type: Mapped[str] = mapped_column(String(64), index=True)
    target: Mapped[str] = mapped_column(Text, default="")
    before_text: Mapped[str] = mapped_column(Text, default="")
    after_text: Mapped[str] = mapped_column(Text, default="")
    rationale: Mapped[str] = mapped_column(Text, default="")
    changed_by: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    document: Mapped[DraftDocument] = relationship(back_populates="changes")
    version: Mapped[DraftDocumentVersion] = relationship(back_populates="changes")


class DraftContextSnapshot(Base):
    __tablename__ = "draft_context_snapshots"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    matter_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    document_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("draft_documents.id", ondelete="CASCADE"),
        index=True,
    )
    query: Mapped[str] = mapped_column(Text, default="")
    source_refs: Mapped[str] = mapped_column(Text, default="[]")
    uploaded_document_ids: Mapped[str] = mapped_column(Text, default="[]")
    retrieved_context: Mapped[str] = mapped_column(Text, default="")
    agent_memory: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    document: Mapped[DraftDocument] = relationship(back_populates="context_snapshots")
    versions: Mapped[list[DraftDocumentVersion]] = relationship(
        back_populates="context_snapshot",
    )
