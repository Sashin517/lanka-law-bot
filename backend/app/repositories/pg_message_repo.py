"""PostgreSQL repository for ordered conversation messages."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from uuid import uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.conversation import (
    AgentRun,
    Conversation,
    ConversationStatus,
    Message,
    MessageAttachment,
    MessageCitation,
    MessageRole,
)
from app.repositories.cursors import decode_cursor, encode_cursor
from app.repositories.exceptions import (
    ConversationNotFoundError,
    InvalidCursorError,
    InvalidRepositoryDataError,
)
from app.repositories.interfaces import MessageRepositoryInterface, RepositoryRecord
from app.repositories.serializers import message_to_record


class PgMessageRepository(MessageRepositoryInterface):
    """Async message persistence with serialized per-conversation appends."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        conversation_id: str,
        role: str,
        content: str,
        *,
        markdown_content: str | None = None,
        confidence: str | None = None,
        disclaimer: str | None = None,
        query_mode: str | None = None,
        agent_run_id: str | None = None,
        citations: Sequence[Mapping[str, Any]] | None = None,
        attachments: Sequence[Mapping[str, Any]] | None = None,
        token_count: int = 0,
    ) -> RepositoryRecord:
        await self._lock_active_conversation(conversation_id)
        message_role = _parse_role(role)
        if isinstance(token_count, bool) or not isinstance(token_count, int):
            raise InvalidRepositoryDataError("token_count must be an integer.")
        if token_count < 0:
            raise InvalidRepositoryDataError("token_count cannot be negative.")
        if agent_run_id is not None:
            await self._validate_agent_run(conversation_id, agent_run_id)

        max_sequence = await self._session.scalar(
            select(func.max(Message.sequence_number)).where(
                Message.conversation_id == conversation_id
            )
        )
        sequence_number = 0 if max_sequence is None else max_sequence + 1

        message = Message(
            id=str(uuid4()),
            conversation_id=conversation_id,
            role=message_role,
            content=content,
            markdown_content=markdown_content,
            confidence=_optional_limited_text(confidence, "confidence", 16),
            disclaimer=disclaimer,
            sequence_number=sequence_number,
            token_count=token_count,
            query_mode=_optional_limited_text(query_mode, "query_mode", 32),
            agent_run_id=agent_run_id,
        )
        message.citations = [
            _build_citation(message.id, item) for item in (citations or ())
        ]
        message.attachments = [
            _build_attachment(message.id, item) for item in (attachments or ())
        ]
        self._session.add(message)
        await self._session.flush()
        return message_to_record(message)

    async def list_by_conversation(
        self,
        conversation_id: str,
        *,
        cursor: str | None = None,
        limit: int = 50,
        order: str = "asc",
    ) -> tuple[list[RepositoryRecord], str | None]:
        _validate_limit(limit, maximum=200)
        if order not in {"asc", "desc"}:
            raise InvalidRepositoryDataError("order must be 'asc' or 'desc'.")

        statement = (
            select(Message)
            .options(
                selectinload(Message.citations),
                selectinload(Message.attachments),
            )
            .where(Message.conversation_id == conversation_id)
        )
        cursor_kind = f"messages:{order}"
        if cursor:
            cursor_sequence, cursor_id = _decode_message_cursor(
                cursor, expected_kind=cursor_kind
            )
            if order == "asc":
                cursor_filter = or_(
                    Message.sequence_number > cursor_sequence,
                    and_(
                        Message.sequence_number == cursor_sequence,
                        Message.id > cursor_id,
                    ),
                )
            else:
                cursor_filter = or_(
                    Message.sequence_number < cursor_sequence,
                    and_(
                        Message.sequence_number == cursor_sequence,
                        Message.id < cursor_id,
                    ),
                )
            statement = statement.where(cursor_filter)

        ordering = (
            (Message.sequence_number.asc(), Message.id.asc())
            if order == "asc"
            else (Message.sequence_number.desc(), Message.id.desc())
        )
        statement = statement.order_by(*ordering).limit(limit + 1)
        messages = list((await self._session.scalars(statement)).all())
        has_more = len(messages) > limit
        page = messages[:limit]

        next_cursor = None
        if has_more and page:
            last = page[-1]
            next_cursor = encode_cursor(
                cursor_kind,
                {"sequence_number": last.sequence_number, "id": last.id},
            )
        return [message_to_record(item) for item in page], next_cursor

    async def get_recent(
        self, conversation_id: str, limit: int = 10
    ) -> list[RepositoryRecord]:
        _validate_limit(limit, maximum=200)
        statement = (
            select(Message)
            .options(
                selectinload(Message.citations),
                selectinload(Message.attachments),
            )
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.sequence_number.desc(), Message.id.desc())
            .limit(limit)
        )
        messages = list((await self._session.scalars(statement)).all())
        messages.reverse()
        return [message_to_record(item) for item in messages]

    async def count_by_conversation(self, conversation_id: str) -> int:
        statement = select(func.count(Message.id)).where(
            Message.conversation_id == conversation_id
        )
        return int((await self._session.scalar(statement)) or 0)

    async def _lock_active_conversation(self, conversation_id: str) -> None:
        """Serialize appends so MAX(sequence_number)+1 remains race-safe."""
        statement = (
            select(Conversation.id)
            .where(
                Conversation.id == conversation_id,
                Conversation.status == ConversationStatus.ACTIVE,
            )
            .with_for_update()
        )
        locked_id = await self._session.scalar(statement)
        if locked_id is None:
            raise ConversationNotFoundError("Active conversation not found.")

    async def _validate_agent_run(
        self, conversation_id: str, agent_run_id: str
    ) -> None:
        await self._session.flush()
        matching_run_id = await self._session.scalar(
            select(AgentRun.id).where(
                AgentRun.id == agent_run_id,
                AgentRun.conversation_id == conversation_id,
            )
        )
        if matching_run_id is None:
            raise InvalidRepositoryDataError(
                "agent_run_id does not belong to this conversation."
            )


def _parse_role(role: str) -> MessageRole:
    try:
        return MessageRole(role)
    except ValueError as exc:
        raise InvalidRepositoryDataError("Unsupported message role.") from exc


def _optional_limited_text(
    value: str | None, field: str, max_length: int
) -> str | None:
    if value is None:
        return None
    if len(value) > max_length:
        raise InvalidRepositoryDataError(
            f"{field} cannot exceed {max_length} characters."
        )
    return value


def _required_mapping_text(item: Mapping[str, Any], field: str, max_length: int) -> str:
    value = item.get(field)
    if not isinstance(value, str) or not value.strip():
        raise InvalidRepositoryDataError(f"{field} is required.")
    value = value.strip()
    if len(value) > max_length:
        raise InvalidRepositoryDataError(
            f"{field} cannot exceed {max_length} characters."
        )
    return value


def _mapping_text(
    item: Mapping[str, Any], field: str, max_length: int | None = None
) -> str | None:
    value = item.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        raise InvalidRepositoryDataError(f"{field} must be a string.")
    if max_length is not None and len(value) > max_length:
        raise InvalidRepositoryDataError(
            f"{field} cannot exceed {max_length} characters."
        )
    return value


def _mapping_nonnegative_int(
    item: Mapping[str, Any], field: str, default: int = 0
) -> int:
    value = item.get(field, default)
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidRepositoryDataError(f"{field} must be an integer.")
    if value < 0:
        raise InvalidRepositoryDataError(f"{field} cannot be negative.")
    return value


def _build_citation(message_id: str, item: Mapping[str, Any]) -> MessageCitation:
    authoritative = item.get("authoritative")
    if authoritative is not None and not isinstance(authoritative, bool):
        raise InvalidRepositoryDataError("authoritative must be a boolean.")
    excerpt = _mapping_text(item, "excerpt")
    if excerpt is None:
        excerpt = _mapping_text(item, "content") or ""

    page_start = (
        _mapping_nonnegative_int(item, "page_start")
        if item.get("page_start") is not None
        else None
    )
    page_end = (
        _mapping_nonnegative_int(item, "page_end")
        if item.get("page_end") is not None
        else None
    )
    if page_start is not None and page_end is not None and page_end < page_start:
        raise InvalidRepositoryDataError("page_end cannot be before page_start.")

    return MessageCitation(
        id=str(uuid4()),
        message_id=message_id,
        citation_id=_required_mapping_text(item, "citation_id", 32),
        title=_mapping_text(item, "title", 512) or "",
        section=_mapping_text(item, "section", 512),
        year=_mapping_nonnegative_int(item, "year"),
        breadcrumb=_mapping_text(item, "breadcrumb"),
        excerpt=excerpt,
        source_type=_mapping_text(item, "source_type", 64),
        document_id=_mapping_text(item, "document_id", 64),
        filename=_mapping_text(item, "filename", 512),
        page_start=page_start,
        page_end=page_end,
        source_uri=_mapping_text(item, "source_uri"),
        court=_mapping_text(item, "court", 256),
        reporter_citation=_mapping_text(item, "reporter_citation", 256),
        docket_number=_mapping_text(item, "docket_number", 128),
        authoritative=authoritative,
    )


def _build_attachment(message_id: str, item: Mapping[str, Any]) -> MessageAttachment:
    return MessageAttachment(
        id=str(uuid4()),
        message_id=message_id,
        document_id=_required_mapping_text(item, "document_id", 64),
        filename=_required_mapping_text(item, "filename", 512),
        status=_mapping_text(item, "status", 32) or "completed",
    )


def _validate_limit(limit: int, *, maximum: int) -> None:
    if limit < 1 or limit > maximum:
        raise InvalidRepositoryDataError(f"limit must be between 1 and {maximum}.")


def _decode_message_cursor(cursor: str, *, expected_kind: str) -> tuple[int, str]:
    values = decode_cursor(cursor, expected_kind=expected_kind)
    sequence_number = values.get("sequence_number")
    message_id = values.get("id")
    if (
        isinstance(sequence_number, bool)
        or not isinstance(sequence_number, int)
        or sequence_number < 0
        or not isinstance(message_id, str)
    ):
        raise InvalidCursorError("Invalid message cursor values.")
    return sequence_number, message_id
