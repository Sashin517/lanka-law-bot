"""PostgreSQL models for persistent research-chat conversations."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.postgres_session import Base


def utcnow() -> datetime:
    """Return an aware UTC timestamp for Python-side defaults."""
    return datetime.now(timezone.utc)


def _enum_values(enum_class: type[PyEnum]) -> list[str]:
    return [str(member.value) for member in enum_class]


class MessageRole(str, PyEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ConversationStatus(str, PyEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"


conversation_status_enum = Enum(
    ConversationStatus,
    name="conversation_status",
    values_callable=_enum_values,
    validate_strings=True,
)
message_role_enum = Enum(
    MessageRole,
    name="message_role",
    values_callable=_enum_values,
    validate_strings=True,
)


class Conversation(Base):
    """A chat conversation owned by one Firebase-authenticated user."""

    __tablename__ = "conversations"
    __table_args__ = (
        CheckConstraint("message_count >= 0", name="message_count_non_negative"),
        Index("ix_conversations_user_updated", "user_id", "updated_at"),
        Index(
            "ix_conversations_title_pattern",
            "title",
            postgresql_ops={"title": "text_pattern_ops"},
        ),
        Index(
            "ix_conversations_user_status_updated_id",
            "user_id",
            "status",
            "updated_at",
            "id",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    title: Mapped[str] = mapped_column(
        String(512), nullable=False, default="New Chat", server_default="New Chat"
    )
    status: Mapped[ConversationStatus] = mapped_column(
        conversation_status_enum,
        nullable=False,
        default=ConversationStatus.ACTIVE,
        server_default=ConversationStatus.ACTIVE.value,
        index=True,
    )
    query_mode: Mapped[str] = mapped_column(
        String(32), nullable=False, default="quick_qa", server_default="quick_qa"
    )
    message_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_message_preview: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=func.now(),
        onupdate=utcnow,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Message.sequence_number",
    )
    summaries: Mapped[list[ConversationSummary]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ConversationSummary.to_sequence",
    )
    agent_runs: Mapped[list[AgentRun]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Message(Base):
    """One ordered user, assistant, or system message in a conversation."""

    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("sequence_number >= 0", name="sequence_non_negative"),
        CheckConstraint("token_count >= 0", name="token_count_non_negative"),
        Index("ix_messages_conv_seq", "conversation_id", "sequence_number"),
        Index(
            "ix_messages_conv_created_id",
            "conversation_id",
            "created_at",
            "id",
        ),
        UniqueConstraint(
            "conversation_id", "sequence_number", name="uq_message_sequence"
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[MessageRole] = mapped_column(message_role_enum, nullable=False)
    content: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    markdown_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(16), nullable=True)
    disclaimer: Mapped[str | None] = mapped_column(Text, nullable=True)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    token_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    query_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    agent_run_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey(
            "agent_runs.id",
            name="fk_messages_agent_run_id_agent_runs",
            ondelete="SET NULL",
            use_alter=True,
        ),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=func.now(),
    )

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
    citations: Mapped[list[MessageCitation]] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    attachments: Mapped[list[MessageAttachment]] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    agent_run: Mapped[AgentRun | None] = relationship(back_populates="messages")


class MessageCitation(Base):
    """Immutable source details captured with an assistant message."""

    __tablename__ = "message_citations"
    __table_args__ = (
        CheckConstraint("year >= 0", name="year_non_negative"),
        CheckConstraint(
            "page_start IS NULL OR page_start >= 0", name="page_start_non_negative"
        ),
        CheckConstraint(
            "page_end IS NULL OR page_end >= 0", name="page_end_non_negative"
        ),
        CheckConstraint(
            "page_start IS NULL OR page_end IS NULL OR page_end >= page_start",
            name="page_range_ordered",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    message_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    citation_id: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(
        String(512), nullable=False, default="", server_default=""
    )
    section: Mapped[str | None] = mapped_column(String(512), nullable=True)
    year: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    breadcrumb: Mapped[str | None] = mapped_column(Text, nullable=True)
    excerpt: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    source_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    document_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    court: Mapped[str | None] = mapped_column(String(256), nullable=True)
    reporter_citation: Mapped[str | None] = mapped_column(String(256), nullable=True)
    docket_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    authoritative: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    message: Mapped[Message] = relationship(back_populates="citations")


class MessageAttachment(Base):
    """Snapshot of an uploaded document attached when a message was sent."""

    __tablename__ = "message_attachments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    message_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_id: Mapped[str] = mapped_column(String(64), nullable=False)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="completed", server_default="completed"
    )

    message: Mapped[Message] = relationship(back_populates="attachments")


class AgentRun(Base):
    """Auditable metadata for one execution of the agent pipeline."""

    __tablename__ = "agent_runs"
    __table_args__ = (
        CheckConstraint("total_steps >= 0", name="total_steps_non_negative"),
        CheckConstraint(
            "grounding_score >= 0.0 AND grounding_score <= 1.0",
            name="grounding_score_range",
        ),
        CheckConstraint("duration_ms >= 0", name="duration_non_negative"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    route: Mapped[str | None] = mapped_column(String(64), nullable=True)
    task_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    answer_mode: Mapped[str | None] = mapped_column(String(64), nullable=True)
    plan_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    steps_executed: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]", server_default="[]"
    )
    total_steps: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    planning_reasoning: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    completed_agents: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]", server_default="[]"
    )
    grounding_score: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, server_default="0"
    )
    duration_ms: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=func.now(),
    )

    conversation: Mapped[Conversation] = relationship(back_populates="agent_runs")
    messages: Mapped[list[Message]] = relationship(
        back_populates="agent_run", passive_deletes=True
    )


class ConversationSummary(Base):
    """Compressed context covering an inclusive message-sequence range."""

    __tablename__ = "conversation_summaries"
    __table_args__ = (
        CheckConstraint("from_sequence >= 0", name="from_sequence_non_negative"),
        CheckConstraint("to_sequence >= from_sequence", name="sequence_range_ordered"),
        CheckConstraint("token_count >= 0", name="token_count_non_negative"),
        UniqueConstraint(
            "conversation_id",
            "from_sequence",
            "to_sequence",
            name="uq_conversation_summary_range",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    summary_text: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    from_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    to_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    token_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=func.now(),
    )

    conversation: Mapped[Conversation] = relationship(back_populates="summaries")
