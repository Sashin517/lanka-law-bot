from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.database.postgres_session import ConversationBase
from app.database.session import Base
from app.models.conversation import (
    AgentRun,
    Conversation,
    ConversationStatus,
    ConversationSummary,
    Message,
    MessageAttachment,
    MessageCitation,
    MessageRole,
)

EXPECTED_TABLES = {
    "agent_runs",
    "conversation_summaries",
    "conversations",
    "message_attachments",
    "message_citations",
    "messages",
}


def test_postgres_dsn_escapes_credentials() -> None:
    config = Settings(
        _env_file=None,
        POSTGRES_USER="legal user",
        POSTGRES_PASSWORD="p@ss:/?#word",
        POSTGRES_HOST="db.internal",
        POSTGRES_PORT=5544,
        POSTGRES_DB="legal_chat",
    )

    parsed = make_url(config.postgres_dsn)

    assert parsed.drivername == "postgresql+asyncpg"
    assert parsed.username == "legal user"
    assert parsed.password == "p@ss:/?#word"
    assert parsed.host == "db.internal"
    assert parsed.port == 5544
    assert parsed.database == "legal_chat"


def test_conversation_metadata_is_isolated_from_sqlite_metadata() -> None:
    assert ConversationBase is not Base
    assert set(ConversationBase.metadata.tables) == EXPECTED_TABLES
    assert EXPECTED_TABLES.isdisjoint(Base.metadata.tables)


def test_models_persist_relationships_and_enum_values() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    ConversationBase.metadata.create_all(engine)

    conversation = Conversation(
        id="conversation-1",
        user_id="firebase-user-1",
        status=ConversationStatus.ACTIVE,
    )
    run = AgentRun(id="run-1", conversation=conversation)
    message = Message(
        id="message-1",
        conversation=conversation,
        agent_run=run,
        role=MessageRole.ASSISTANT,
        content="The answer.",
        sequence_number=0,
        citations=[
            MessageCitation(
                id="citation-1",
                citation_id="LAW-1",
                title="Evidence Ordinance",
                year=1895,
                excerpt="Relevant excerpt",
                authoritative=True,
            )
        ],
        attachments=[
            MessageAttachment(
                id="attachment-1",
                document_id="document-1",
                filename="evidence.pdf",
            )
        ],
    )
    summary = ConversationSummary(
        id="summary-1",
        conversation=conversation,
        summary_text="Earlier discussion.",
        from_sequence=0,
        to_sequence=0,
    )

    with Session(engine) as session:
        session.add_all([conversation, message, summary])
        session.commit()
        session.expire_all()

        stored = session.get(Conversation, "conversation-1")
        assert stored is not None
        assert stored.status is ConversationStatus.ACTIVE
        assert stored.messages[0].role is MessageRole.ASSISTANT
        assert stored.messages[0].citations[0].citation_id == "LAW-1"
        assert stored.messages[0].attachments[0].document_id == "document-1"
        assert stored.summaries[0].summary_text == "Earlier discussion."
        assert stored.agent_runs[0].id == "run-1"


def test_cursor_pagination_indexes_are_present() -> None:
    conversation_indexes = {index.name for index in Conversation.__table__.indexes}
    message_indexes = {index.name for index in Message.__table__.indexes}

    assert "ix_conversations_user_status_updated_id" in conversation_indexes
    assert "ix_conversations_title_pattern" in conversation_indexes
    assert "ix_messages_conv_created_id" in message_indexes
    assert "ix_messages_conv_seq" in message_indexes
