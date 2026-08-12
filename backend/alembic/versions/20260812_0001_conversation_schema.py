"""Create the PostgreSQL conversation persistence schema.

Revision ID: 20260812_0001
Revises: None
Create Date: 2026-08-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260812_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


conversation_status = postgresql.ENUM(
    "active", "archived", "deleted", name="conversation_status", create_type=False
)
message_role = postgresql.ENUM(
    "user", "assistant", "system", name="message_role", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    conversation_status.create(bind, checkfirst=True)
    message_role.create(bind, checkfirst=True)

    op.create_table(
        "conversations",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column(
            "title", sa.String(length=512), server_default="New Chat", nullable=False
        ),
        sa.Column(
            "status", conversation_status, server_default="active", nullable=False
        ),
        sa.Column(
            "query_mode",
            sa.String(length=32),
            server_default="quick_qa",
            nullable=False,
        ),
        sa.Column("message_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_message_preview", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("message_count >= 0", name="message_count_non_negative"),
        sa.PrimaryKeyConstraint("id", name="pk_conversations"),
    )
    op.create_index("ix_conversations_status", "conversations", ["status"])
    op.create_index(
        "ix_conversations_title_pattern",
        "conversations",
        ["title"],
        postgresql_ops={"title": "text_pattern_ops"},
    )
    op.create_index("ix_conversations_user_id", "conversations", ["user_id"])
    op.create_index(
        "ix_conversations_user_updated", "conversations", ["user_id", "updated_at"]
    )
    op.create_index(
        "ix_conversations_user_status_updated_id",
        "conversations",
        ["user_id", "status", "updated_at", "id"],
    )

    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("conversation_id", sa.String(length=64), nullable=False),
        sa.Column("route", sa.String(length=64), nullable=True),
        sa.Column("task_type", sa.String(length=64), nullable=True),
        sa.Column("answer_mode", sa.String(length=64), nullable=True),
        sa.Column("plan_type", sa.String(length=32), nullable=True),
        sa.Column("steps_executed", sa.Text(), server_default="[]", nullable=False),
        sa.Column("total_steps", sa.Integer(), server_default="0", nullable=False),
        sa.Column("planning_reasoning", sa.Text(), server_default="", nullable=False),
        sa.Column("completed_agents", sa.Text(), server_default="[]", nullable=False),
        sa.Column("grounding_score", sa.Float(), server_default="0", nullable=False),
        sa.Column("duration_ms", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("duration_ms >= 0", name="duration_non_negative"),
        sa.CheckConstraint(
            "grounding_score >= 0.0 AND grounding_score <= 1.0",
            name="grounding_score_range",
        ),
        sa.CheckConstraint("total_steps >= 0", name="total_steps_non_negative"),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name="fk_agent_runs_conversation_id_conversations",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_agent_runs"),
    )
    op.create_index("ix_agent_runs_conversation_id", "agent_runs", ["conversation_id"])

    op.create_table(
        "conversation_summaries",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("conversation_id", sa.String(length=64), nullable=False),
        sa.Column("summary_text", sa.Text(), server_default="", nullable=False),
        sa.Column("from_sequence", sa.Integer(), nullable=False),
        sa.Column("to_sequence", sa.Integer(), nullable=False),
        sa.Column("token_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("from_sequence >= 0", name="from_sequence_non_negative"),
        sa.CheckConstraint(
            "to_sequence >= from_sequence", name="sequence_range_ordered"
        ),
        sa.CheckConstraint("token_count >= 0", name="token_count_non_negative"),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name="fk_conversation_summaries_conversation_id_conversations",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_conversation_summaries"),
        sa.UniqueConstraint(
            "conversation_id",
            "from_sequence",
            "to_sequence",
            name="uq_conversation_summary_range",
        ),
    )
    op.create_index(
        "ix_conversation_summaries_conversation_id",
        "conversation_summaries",
        ["conversation_id"],
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("conversation_id", sa.String(length=64), nullable=False),
        sa.Column("role", message_role, nullable=False),
        sa.Column("content", sa.Text(), server_default="", nullable=False),
        sa.Column("markdown_content", sa.Text(), nullable=True),
        sa.Column("confidence", sa.String(length=16), nullable=True),
        sa.Column("disclaimer", sa.Text(), nullable=True),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("token_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("query_mode", sa.String(length=32), nullable=True),
        sa.Column("agent_run_id", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("sequence_number >= 0", name="sequence_non_negative"),
        sa.CheckConstraint("token_count >= 0", name="token_count_non_negative"),
        sa.ForeignKeyConstraint(
            ["agent_run_id"],
            ["agent_runs.id"],
            name="fk_messages_agent_run_id_agent_runs",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name="fk_messages_conversation_id_conversations",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_messages"),
        sa.UniqueConstraint(
            "conversation_id", "sequence_number", name="uq_message_sequence"
        ),
    )
    op.create_index("ix_messages_agent_run_id", "messages", ["agent_run_id"])
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])
    op.create_index(
        "ix_messages_conv_seq", "messages", ["conversation_id", "sequence_number"]
    )
    op.create_index(
        "ix_messages_conv_created_id",
        "messages",
        ["conversation_id", "created_at", "id"],
    )

    op.create_table(
        "message_attachments",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("message_id", sa.String(length=64), nullable=False),
        sa.Column("document_id", sa.String(length=64), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column(
            "status", sa.String(length=32), server_default="completed", nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.id"],
            name="fk_message_attachments_message_id_messages",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_message_attachments"),
    )
    op.create_index(
        "ix_message_attachments_message_id", "message_attachments", ["message_id"]
    )

    op.create_table(
        "message_citations",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("message_id", sa.String(length=64), nullable=False),
        sa.Column("citation_id", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=512), server_default="", nullable=False),
        sa.Column("section", sa.String(length=512), nullable=True),
        sa.Column("year", sa.Integer(), server_default="0", nullable=False),
        sa.Column("breadcrumb", sa.Text(), nullable=True),
        sa.Column("excerpt", sa.Text(), server_default="", nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=True),
        sa.Column("document_id", sa.String(length=64), nullable=True),
        sa.Column("filename", sa.String(length=512), nullable=True),
        sa.Column("page_start", sa.Integer(), nullable=True),
        sa.Column("page_end", sa.Integer(), nullable=True),
        sa.Column("source_uri", sa.Text(), nullable=True),
        sa.Column("court", sa.String(length=256), nullable=True),
        sa.Column("reporter_citation", sa.String(length=256), nullable=True),
        sa.Column("docket_number", sa.String(length=128), nullable=True),
        sa.Column("authoritative", sa.Boolean(), nullable=True),
        sa.CheckConstraint(
            "page_end IS NULL OR page_end >= 0", name="page_end_non_negative"
        ),
        sa.CheckConstraint(
            "page_start IS NULL OR page_end IS NULL OR page_end >= page_start",
            name="page_range_ordered",
        ),
        sa.CheckConstraint(
            "page_start IS NULL OR page_start >= 0", name="page_start_non_negative"
        ),
        sa.CheckConstraint("year >= 0", name="year_non_negative"),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.id"],
            name="fk_message_citations_message_id_messages",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_message_citations"),
    )
    op.create_index(
        "ix_message_citations_message_id", "message_citations", ["message_id"]
    )


def downgrade() -> None:
    op.drop_table("message_citations")
    op.drop_table("message_attachments")
    op.drop_table("messages")
    op.drop_table("conversation_summaries")
    op.drop_table("agent_runs")
    op.drop_table("conversations")

    bind = op.get_bind()
    message_role.drop(bind, checkfirst=True)
    conversation_status.drop(bind, checkfirst=True)
