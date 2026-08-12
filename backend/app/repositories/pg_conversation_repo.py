"""PostgreSQL repository for the Conversation aggregate root."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation, ConversationStatus, utcnow
from app.repositories.cursors import decode_cursor, encode_cursor
from app.repositories.exceptions import (
    ConversationNotFoundError,
    InvalidCursorError,
    InvalidRepositoryDataError,
)
from app.repositories.interfaces import (
    ConversationRepositoryInterface,
    RepositoryRecord,
)
from app.repositories.serializers import conversation_to_record


class PgConversationRepository(ConversationRepositoryInterface):
    """SQLAlchemy async implementation with ownership-safe keyset queries."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, user_id: str, title: str, query_mode: str
    ) -> RepositoryRecord:
        conversation = Conversation(
            id=str(uuid4()),
            user_id=_required_text(user_id, "user_id", 128),
            title=_required_text(title, "title", 512),
            query_mode=_required_text(query_mode, "query_mode", 32),
        )
        self._session.add(conversation)
        await self._session.flush()
        return conversation_to_record(conversation)

    async def get_by_id(
        self, conversation_id: str, user_id: str
    ) -> RepositoryRecord | None:
        statement = select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
            Conversation.status != ConversationStatus.DELETED,
        )
        conversation = await self._session.scalar(statement)
        return conversation_to_record(conversation) if conversation else None

    async def list_by_user(
        self,
        user_id: str,
        *,
        cursor: str | None = None,
        limit: int = 30,
        status: str = "active",
    ) -> tuple[list[RepositoryRecord], str | None]:
        _validate_limit(limit, maximum=100)
        try:
            status_value = ConversationStatus(status)
        except ValueError as exc:
            raise InvalidRepositoryDataError(
                "Unsupported conversation status."
            ) from exc

        statement = select(Conversation).where(
            Conversation.user_id == user_id,
            Conversation.status == status_value,
        )
        cursor_kind = f"conversations:{status_value.value}"
        if cursor:
            cursor_updated_at, cursor_id = _decode_conversation_cursor(
                cursor, expected_kind=cursor_kind
            )
            statement = statement.where(
                or_(
                    Conversation.updated_at < cursor_updated_at,
                    and_(
                        Conversation.updated_at == cursor_updated_at,
                        Conversation.id < cursor_id,
                    ),
                )
            )

        statement = statement.order_by(
            Conversation.updated_at.desc(), Conversation.id.desc()
        ).limit(limit + 1)
        conversations = list((await self._session.scalars(statement)).all())
        has_more = len(conversations) > limit
        page = conversations[:limit]

        next_cursor = None
        if has_more and page:
            last = page[-1]
            next_cursor = encode_cursor(
                cursor_kind,
                {
                    "updated_at": _as_utc(last.updated_at).isoformat(),
                    "id": last.id,
                },
            )
        return [conversation_to_record(item) for item in page], next_cursor

    async def update_title(
        self, conversation_id: str, user_id: str, title: str
    ) -> None:
        statement = (
            update(Conversation)
            .where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
                Conversation.status != ConversationStatus.DELETED,
            )
            .values(title=_required_text(title, "title", 512), updated_at=utcnow())
        )
        result = await self._session.execute(statement)
        if result.rowcount != 1:
            raise ConversationNotFoundError("Conversation not found.")

    async def update_metadata(
        self,
        conversation_id: str,
        *,
        message_count: int | None = None,
        last_message_preview: str | None = None,
    ) -> None:
        values: dict[str, object] = {"updated_at": utcnow()}
        if message_count is not None:
            if message_count < 0:
                raise InvalidRepositoryDataError("message_count cannot be negative.")
            values["message_count"] = message_count
        if last_message_preview is not None:
            values["last_message_preview"] = last_message_preview

        statement = (
            update(Conversation)
            .where(
                Conversation.id == conversation_id,
                Conversation.status == ConversationStatus.ACTIVE,
            )
            .values(**values)
        )
        result = await self._session.execute(statement)
        if result.rowcount != 1:
            raise ConversationNotFoundError("Active conversation not found.")

    async def soft_delete(self, conversation_id: str, user_id: str) -> None:
        deleted_at = utcnow()
        statement = (
            update(Conversation)
            .where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
                Conversation.status != ConversationStatus.DELETED,
            )
            .values(
                status=ConversationStatus.DELETED,
                deleted_at=deleted_at,
                updated_at=deleted_at,
            )
        )
        result = await self._session.execute(statement)
        if result.rowcount != 1:
            raise ConversationNotFoundError("Conversation not found.")


def _required_text(value: str, field: str, max_length: int) -> str:
    normalized = value.strip()
    if not normalized:
        raise InvalidRepositoryDataError(f"{field} cannot be empty.")
    if len(normalized) > max_length:
        raise InvalidRepositoryDataError(
            f"{field} cannot exceed {max_length} characters."
        )
    return normalized


def _validate_limit(limit: int, *, maximum: int) -> None:
    if limit < 1 or limit > maximum:
        raise InvalidRepositoryDataError(f"limit must be between 1 and {maximum}.")


def _decode_conversation_cursor(
    cursor: str, *, expected_kind: str
) -> tuple[datetime, str]:
    values = decode_cursor(cursor, expected_kind=expected_kind)
    updated_at = values.get("updated_at")
    conversation_id = values.get("id")
    if not isinstance(updated_at, str) or not isinstance(conversation_id, str):
        raise InvalidCursorError("Invalid conversation cursor values.")
    try:
        parsed = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InvalidCursorError("Invalid conversation cursor timestamp.") from exc
    return _as_utc(parsed), conversation_id


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
