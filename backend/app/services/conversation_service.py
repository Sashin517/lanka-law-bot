"""Business service for conversation lifecycle and message persistence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.repositories.exceptions import ConversationNotFoundError
from app.repositories.interfaces import RepositoryRecord, UnitOfWorkInterface
from app.repositories.unit_of_work import UnitOfWork
from app.services.memory_service import MemoryService
from app.utils.token_counter import count_tokens

VALID_QUERY_MODES = frozenset(
    {"quick_qa", "deep_research", "drafting", "review", "reasoning"}
)


class ConversationService:
    """Coordinate conversation use cases without executing the agent graph."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        unit_of_work: UnitOfWorkInterface | None = None,
        memory_service: MemoryService | None = None,
    ) -> None:
        self._uow = unit_of_work or UnitOfWork(session)
        self._memory = memory_service or MemoryService(
            session, messages=self._uow.messages
        )

    async def create_conversation(
        self,
        user_id: str,
        title: str = "New Chat",
        query_mode: str = "quick_qa",
    ) -> RepositoryRecord:
        _validate_query_mode(query_mode)
        _validate_required_text(user_id, "user_id", 128)
        _validate_required_text(title, "title", 512)
        async with self._uow:
            conversation = await self._uow.conversations.create(
                user_id, title, query_mode
            )
            await self._uow.commit()
        return conversation

    async def get_conversation(
        self, conversation_id: str, user_id: str
    ) -> RepositoryRecord | None:
        return await self._uow.conversations.get_by_id(conversation_id, user_id)

    async def list_conversations(
        self,
        user_id: str,
        cursor: str | None = None,
        limit: int = 30,
    ) -> tuple[list[RepositoryRecord], str | None]:
        return await self._uow.conversations.list_by_user(
            user_id, cursor=cursor, limit=limit
        )

    async def rename_conversation(
        self, conversation_id: str, user_id: str, title: str
    ) -> None:
        _validate_required_text(title, "title", 512)
        async with self._uow:
            await self._uow.conversations.update_title(conversation_id, user_id, title)
            await self._uow.commit()

    async def delete_conversation(self, conversation_id: str, user_id: str) -> None:
        async with self._uow:
            await self._uow.conversations.soft_delete(conversation_id, user_id)
            await self._uow.commit()

    async def add_user_message(
        self,
        conversation_id: str,
        content: str,
        *,
        user_id: str,
        attachments: Sequence[Mapping[str, Any]] | None = None,
        query_mode: str | None = None,
        token_count: int | None = None,
    ) -> RepositoryRecord:
        _validate_required_text(content, "content", None)
        if query_mode is not None:
            _validate_query_mode(query_mode)

        async with self._uow:
            conversation = await self._require_owned_active(conversation_id, user_id)
            message = await self._uow.messages.create(
                conversation_id=conversation_id,
                role="user",
                content=content,
                query_mode=query_mode,
                attachments=attachments,
                token_count=count_tokens(content)
                if token_count is None
                else token_count,
            )
            count = await self._update_conversation_metadata(conversation_id, content)
            await self._maybe_auto_title(
                conversation=conversation,
                conversation_id=conversation_id,
                user_id=user_id,
                message_count=count,
            )
            await self._uow.commit()
        return message

    async def add_assistant_message(
        self,
        conversation_id: str,
        content: str,
        *,
        user_id: str,
        markdown_content: str | None = None,
        confidence: str | None = None,
        disclaimer: str | None = None,
        citations: Sequence[Mapping[str, Any]] | None = None,
        agent_run_id: str | None = None,
        agent_run: Mapping[str, Any] | None = None,
        token_count: int | None = None,
    ) -> RepositoryRecord:
        _validate_required_text(content, "content", None)
        if agent_run_id is not None and agent_run is not None:
            raise ValueError("Provide either agent_run_id or agent_run, not both.")
        async with self._uow:
            conversation = await self._require_owned_active(conversation_id, user_id)
            if agent_run is not None:
                run = await self._uow.agent_runs.create(
                    conversation_id,
                    **_agent_run_arguments(agent_run),
                )
                agent_run_id = run["id"]
            message = await self._uow.messages.create(
                conversation_id=conversation_id,
                role="assistant",
                content=content,
                markdown_content=markdown_content,
                confidence=confidence,
                disclaimer=disclaimer,
                citations=citations,
                agent_run_id=agent_run_id,
                token_count=count_tokens(content)
                if token_count is None
                else token_count,
            )
            count = await self._update_conversation_metadata(conversation_id, content)
            await self._maybe_auto_title(
                conversation=conversation,
                conversation_id=conversation_id,
                user_id=user_id,
                message_count=count,
            )
            await self._memory.maybe_summarise(conversation_id)
            await self._uow.commit()
        return message

    async def get_messages(
        self,
        conversation_id: str,
        *,
        user_id: str,
        cursor: str | None = None,
        limit: int = 50,
        order: str = "asc",
    ) -> tuple[list[RepositoryRecord], str | None]:
        await self._require_owned_active(conversation_id, user_id)
        return await self._uow.messages.list_by_conversation(
            conversation_id, cursor=cursor, limit=limit, order=order
        )

    async def build_context_window(
        self,
        conversation_id: str,
        *,
        user_id: str,
        mode: str = "quick_qa",
        exclude_message_id: str | None = None,
    ) -> list[dict[str, str]]:
        _validate_query_mode(mode)
        await self._require_owned_active(conversation_id, user_id)
        return await self._memory.build_context(
            conversation_id,
            mode,
            exclude_message_id=exclude_message_id,
        )

    async def _require_owned_active(
        self, conversation_id: str, user_id: str
    ) -> RepositoryRecord:
        conversation = await self._uow.conversations.get_by_id(conversation_id, user_id)
        if conversation is None or conversation.get("status") != "active":
            raise ConversationNotFoundError("Active conversation not found.")
        return conversation

    async def _update_conversation_metadata(
        self, conversation_id: str, content: str
    ) -> int:
        count = await self._uow.messages.count_by_conversation(conversation_id)
        await self._uow.conversations.update_metadata(
            conversation_id,
            message_count=count,
            last_message_preview=content[:200],
        )
        return count

    async def _maybe_auto_title(
        self,
        *,
        conversation: RepositoryRecord,
        conversation_id: str,
        user_id: str,
        message_count: int,
    ) -> None:
        if (
            conversation.get("title") != "New Chat"
            or message_count < settings.AUTO_TITLE_AFTER_MESSAGES
        ):
            return

        recent = await self._uow.messages.get_recent(
            conversation_id, limit=settings.AUTO_TITLE_AFTER_MESSAGES
        )
        first_user_content = next(
            (
                item.get("content")
                for item in recent
                if item.get("role") == "user" and item.get("content")
            ),
            None,
        )
        if not isinstance(first_user_content, str):
            return
        title = _build_auto_title(first_user_content)
        if title:
            await self._uow.conversations.update_title(conversation_id, user_id, title)


def _validate_query_mode(query_mode: str) -> None:
    if query_mode not in VALID_QUERY_MODES:
        raise ValueError(f"Unsupported query mode: {query_mode!r}.")


def _validate_required_text(value: str, field: str, max_length: int | None) -> None:
    if not value.strip():
        raise ValueError(f"{field} cannot be empty.")
    if max_length is not None and len(value.strip()) > max_length:
        raise ValueError(f"{field} cannot exceed {max_length} characters.")


def _build_auto_title(first_message: str) -> str:
    normalized = " ".join(first_message.split())
    if len(normalized) <= 60:
        return normalized
    return f"{normalized[:60].rstrip()}…"


def _agent_run_arguments(metadata: Mapping[str, Any]) -> dict[str, Any]:
    """Allow only the stable repository contract across the service boundary."""
    allowed = {
        "route",
        "task_type",
        "answer_mode",
        "plan_type",
        "steps_executed",
        "total_steps",
        "planning_reasoning",
        "completed_agents",
        "grounding_score",
        "duration_ms",
    }
    return {key: value for key, value in metadata.items() if key in allowed}
