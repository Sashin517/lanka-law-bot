"""Move document and drafting metadata persistence to PostgreSQL.

Revision ID: 20260812_0002
Revises: 20260812_0001
Create Date: 2026-08-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260812_0002"
down_revision: str | None = "20260812_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_documents",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("matter_id", sa.String(length=128), nullable=True),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=True),
        sa.Column("stored_path", sa.Text(), nullable=False),
        sa.Column("markdown_path", sa.Text(), nullable=True),
        sa.Column("mime_type", sa.String(length=255), nullable=True),
        sa.Column("file_hash", sa.String(length=64), nullable=False),
        sa.Column("document_type", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_user_documents"),
    )
    _create_indexes(
        "user_documents",
        ("tenant_id", "user_id", "matter_id", "file_hash", "status"),
    )

    op.create_table(
        "ingestion_jobs",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("document_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["user_documents.id"],
            name="fk_ingestion_jobs_document_id_user_documents",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ingestion_jobs"),
    )
    _create_indexes("ingestion_jobs", ("document_id", "status"))

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("document_id", sa.String(length=64), nullable=False),
        sa.Column("parent_id", sa.String(length=128), nullable=True),
        sa.Column("chunk_type", sa.String(length=64), nullable=False),
        sa.Column("chunk_strategy", sa.String(length=128), nullable=False),
        sa.Column("vector_record_id", sa.String(length=64), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=True),
        sa.Column("page_end", sa.Integer(), nullable=True),
        sa.Column("heading_path", sa.Text(), nullable=True),
        sa.Column("clause_label", sa.String(length=255), nullable=True),
        sa.Column("text_hash", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["user_documents.id"],
            name="fk_document_chunks_document_id_user_documents",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document_chunks"),
    )
    _create_indexes(
        "document_chunks",
        ("document_id", "parent_id", "chunk_type", "vector_record_id", "text_hash"),
    )

    op.create_table(
        "draft_documents",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("matter_id", sa.String(length=128), nullable=True),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("document_type", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("editor_json", sa.Text(), nullable=False),
        sa.Column("markdown_content", sa.Text(), nullable=False),
        sa.Column("html_content", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_draft_documents"),
    )
    _create_indexes(
        "draft_documents",
        (
            "tenant_id",
            "user_id",
            "matter_id",
            "document_type",
            "status",
            "created_by",
        ),
    )

    op.create_table(
        "draft_context_snapshots",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("matter_id", sa.String(length=128), nullable=True),
        sa.Column("document_id", sa.String(length=64), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("source_refs", sa.Text(), nullable=False),
        sa.Column("uploaded_document_ids", sa.Text(), nullable=False),
        sa.Column("retrieved_context", sa.Text(), nullable=False),
        sa.Column("agent_memory", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["draft_documents.id"],
            name="fk_draft_context_snapshots_document_id_draft_documents",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_draft_context_snapshots"),
    )
    _create_indexes("draft_context_snapshots", ("matter_id", "document_id"))

    op.create_table(
        "draft_document_versions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("document_id", sa.String(length=64), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("editor_json", sa.Text(), nullable=False),
        sa.Column("markdown_content", sa.Text(), nullable=False),
        sa.Column("source_refs", sa.Text(), nullable=False),
        sa.Column("change_summary", sa.Text(), nullable=False),
        sa.Column("changed_by", sa.String(length=32), nullable=False),
        sa.Column("parent_version_id", sa.String(length=64), nullable=True),
        sa.Column("agent_run_id", sa.String(length=128), nullable=True),
        sa.Column("context_snapshot_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["context_snapshot_id"],
            ["draft_context_snapshots.id"],
            name=op.f(
                "fk_draft_document_versions_context_snapshot_id_"
                "draft_context_snapshots"
            ),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["draft_documents.id"],
            name=op.f(
                "fk_draft_document_versions_document_id_draft_documents"
            ),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_version_id"],
            ["draft_document_versions.id"],
            name=op.f(
                "fk_draft_document_versions_parent_version_id_"
                "draft_document_versions"
            ),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_draft_document_versions"),
        sa.UniqueConstraint(
            "document_id",
            "version_number",
            name="uq_draft_version_number",
        ),
    )
    _create_indexes(
        "draft_document_versions",
        (
            "document_id",
            "changed_by",
            "parent_version_id",
            "agent_run_id",
            "context_snapshot_id",
        ),
    )

    op.create_table(
        "draft_document_changes",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("document_id", sa.String(length=64), nullable=False),
        sa.Column("version_id", sa.String(length=64), nullable=False),
        sa.Column("operation_type", sa.String(length=64), nullable=False),
        sa.Column("target", sa.Text(), nullable=False),
        sa.Column("before_text", sa.Text(), nullable=False),
        sa.Column("after_text", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("changed_by", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["draft_documents.id"],
            name=op.f(
                "fk_draft_document_changes_document_id_draft_documents"
            ),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["draft_document_versions.id"],
            name=op.f(
                "fk_draft_document_changes_version_id_"
                "draft_document_versions"
            ),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_draft_document_changes"),
    )
    _create_indexes(
        "draft_document_changes",
        ("document_id", "version_id", "operation_type", "changed_by"),
    )


def downgrade() -> None:
    op.drop_table("draft_document_changes")
    op.drop_table("draft_document_versions")
    op.drop_table("draft_context_snapshots")
    op.drop_table("draft_documents")
    op.drop_table("document_chunks")
    op.drop_table("ingestion_jobs")
    op.drop_table("user_documents")


def _create_indexes(table_name: str, columns: tuple[str, ...]) -> None:
    for column in columns:
        op.create_index(f"ix_{table_name}_{column}", table_name, [column])
