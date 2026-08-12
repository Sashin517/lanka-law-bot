"""Conversation memory, context strategies, and incremental summarisation."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from bisect import bisect_left
from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.conversation import (
    Conversation,
    ConversationStatus,
    ConversationSummary,
    Message,
)
from app.repositories.interfaces import MessageRepositoryInterface, RepositoryRecord
from app.repositories.pg_message_repo import PgMessageRepository
from app.utils.token_counter import (
    count_tokens,
    truncate_middle_to_token_budget,
    truncate_to_token_budget,
)

logger = logging.getLogger(__name__)

ContextMessage = dict[str, str]


@dataclass(frozen=True, slots=True)
class ContextBudget:
    """Per-mode allocation that reserves the remaining model window for RAG."""

    recent_tokens: int
    recent_message_limit: int
    summary_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.recent_tokens + self.summary_tokens


class ContextWindowStrategy(ABC):
    """Strategy contract for constructing LLM conversation context."""

    @abstractmethod
    async def build(
        self,
        conversation_id: str,
        session: AsyncSession,
        messages: MessageRepositoryInterface,
        max_tokens: int,
        exclude_message_id: str | None = None,
    ) -> list[ContextMessage]: ...


class SlidingWindowStrategy(ContextWindowStrategy):
    """Return the largest recent chronological suffix within the budget."""

    def __init__(self, window_size: int = 10) -> None:
        if window_size < 1:
            raise ValueError("window_size must be positive.")
        self._window_size = window_size

    async def build(
        self,
        conversation_id: str,
        session: AsyncSession,
        messages: MessageRepositoryInterface,
        max_tokens: int,
        exclude_message_id: str | None = None,
    ) -> list[ContextMessage]:
        del session  # The repository owns data access for this strategy.
        recent = await messages.get_recent(conversation_id, limit=self._window_size)
        recent = _exclude_message(recent, exclude_message_id)
        return _records_to_context(_fit_recent_records(recent, max_tokens))


class SummarisedWindowStrategy(ContextWindowStrategy):
    """Combine the latest cumulative summary with a recent message suffix."""

    def __init__(
        self,
        recent_limit: int = 10,
        *,
        summary_max_tokens: int = 800,
        recent_max_tokens: int = 1600,
    ) -> None:
        if recent_limit < 1:
            raise ValueError("recent_limit must be positive.")
        if summary_max_tokens < 0 or recent_max_tokens < 1:
            raise ValueError("Context token allocations must be valid.")
        self._recent_limit = recent_limit
        self._summary_max_tokens = summary_max_tokens
        self._recent_max_tokens = recent_max_tokens

    async def build(
        self,
        conversation_id: str,
        session: AsyncSession,
        messages: MessageRepositoryInterface,
        max_tokens: int,
        exclude_message_id: str | None = None,
    ) -> list[ContextMessage]:
        if max_tokens < 1:
            return []

        summary = await session.scalar(
            select(ConversationSummary)
            .where(ConversationSummary.conversation_id == conversation_id)
            .order_by(
                ConversationSummary.to_sequence.desc(),
                ConversationSummary.created_at.desc(),
            )
            .limit(1)
        )
        context: list[ContextMessage] = []
        remaining_budget = max_tokens

        if summary is not None and self._summary_max_tokens > 0:
            summary_content = f"[Conversation summary so far]: {summary.summary_text}"
            summary_budget = min(self._summary_max_tokens, remaining_budget)
            summary_content = _truncate_to_budget(summary_content, summary_budget)
            if summary_content:
                summary_cost = _estimate_token_count(summary_content)
                context.append({"role": "system", "content": summary_content})
                remaining_budget = max(0, remaining_budget - summary_cost)

        recent = await messages.get_recent(conversation_id, limit=self._recent_limit)
        recent = _exclude_message(recent, exclude_message_id)
        if summary is not None:
            recent = [
                item for item in recent if _record_sequence(item) > summary.to_sequence
            ]
        recent_budget = min(self._recent_max_tokens, remaining_budget)
        context.extend(_records_to_context(_fit_recent_records(recent, recent_budget)))
        return context


class ContextWindowBuilder:
    """Factory Method selecting a context strategy for each query mode."""

    _BUDGETS: ClassVar[dict[str, ContextBudget]] = {
        "quick_qa": ContextBudget(recent_tokens=1200, recent_message_limit=6),
        "deep_research": ContextBudget(
            summary_tokens=800, recent_tokens=1600, recent_message_limit=10
        ),
        "reasoning": ContextBudget(
            summary_tokens=800, recent_tokens=1600, recent_message_limit=10
        ),
        "drafting": ContextBudget(recent_tokens=800, recent_message_limit=4),
        "review": ContextBudget(recent_tokens=1600, recent_message_limit=8),
    }

    @classmethod
    def for_mode(cls, mode: str) -> ContextWindowStrategy:
        budget = cls.budget_for_mode(mode)
        if budget.summary_tokens:
            return SummarisedWindowStrategy(
                recent_limit=budget.recent_message_limit,
                summary_max_tokens=budget.summary_tokens,
                recent_max_tokens=budget.recent_tokens,
            )
        return SlidingWindowStrategy(window_size=budget.recent_message_limit)

    @classmethod
    def budget_for_mode(cls, mode: str) -> ContextBudget:
        return cls._BUDGETS.get(mode, cls._BUDGETS["quick_qa"])


class MemoryService:
    """Orchestrate context construction and incremental summary snapshots."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        messages: MessageRepositoryInterface | None = None,
    ) -> None:
        self._session = session
        self._messages = messages or PgMessageRepository(session)

    async def build_context(
        self,
        conversation_id: str,
        mode: str = "quick_qa",
        *,
        exclude_message_id: str | None = None,
    ) -> list[ContextMessage]:
        strategy = ContextWindowBuilder.for_mode(mode)
        budget = ContextWindowBuilder.budget_for_mode(mode)
        return await strategy.build(
            conversation_id,
            self._session,
            self._messages,
            max_tokens=min(
                settings.CONTEXT_WINDOW_MAX_TOKENS,
                budget.total_tokens,
            ),
            exclude_message_id=exclude_message_id,
        )

    async def maybe_summarise(self, conversation_id: str) -> bool:
        """Persist one cumulative summary when a full unsummarised batch exists.

        The caller owns the surrounding transaction. Locking the conversation
        prevents two concurrent assistant writes from creating the same range.
        """
        locked_conversation = await self._session.scalar(
            select(Conversation.id)
            .where(
                Conversation.id == conversation_id,
                Conversation.status != ConversationStatus.DELETED,
            )
            .with_for_update()
        )
        if locked_conversation is None:
            return False

        latest_summary = await self._session.scalar(
            select(ConversationSummary)
            .where(ConversationSummary.conversation_id == conversation_id)
            .order_by(
                ConversationSummary.to_sequence.desc(),
                ConversationSummary.created_at.desc(),
            )
            .limit(1)
        )
        next_sequence = 0 if latest_summary is None else latest_summary.to_sequence + 1
        batch = list(
            (
                await self._session.scalars(
                    select(Message)
                    .where(
                        Message.conversation_id == conversation_id,
                        Message.sequence_number >= next_sequence,
                    )
                    .order_by(Message.sequence_number.asc())
                    .limit(settings.SUMMARY_TRIGGER_MESSAGE_COUNT)
                )
            ).all()
        )
        if len(batch) < settings.SUMMARY_TRIGGER_MESSAGE_COUNT:
            return False

        summary_text = _build_cumulative_summary(latest_summary, batch)
        new_summary = ConversationSummary(
            id=str(uuid4()),
            conversation_id=conversation_id,
            summary_text=summary_text,
            from_sequence=(
                batch[0].sequence_number
                if latest_summary is None
                else latest_summary.from_sequence
            ),
            to_sequence=batch[-1].sequence_number,
            token_count=count_tokens(summary_text),
        )
        self._session.add(new_summary)
        await self._session.flush()
        logger.info(
            "Summarised messages %d-%d for conversation %s",
            next_sequence,
            new_summary.to_sequence,
            conversation_id,
        )
        return True


def _fit_recent_records(
    records: Sequence[RepositoryRecord], max_tokens: int
) -> list[RepositoryRecord]:
    """Find the largest fitting suffix using prefix sums and binary search."""
    if not records or max_tokens < 1:
        return []

    prefix_costs = [0]
    for record in records:
        prefix_costs.append(prefix_costs[-1] + _record_token_cost(record))

    total_cost = prefix_costs[-1]
    minimum_prefix = max(0, total_cost - max_tokens)
    start_index = bisect_left(prefix_costs, minimum_prefix)
    if start_index >= len(records):
        return []
    return list(records[start_index:])


def _exclude_message(
    records: Sequence[RepositoryRecord], message_id: str | None
) -> list[RepositoryRecord]:
    if message_id is None:
        return list(records)
    return [record for record in records if record.get("id") != message_id]


def _records_to_context(records: Sequence[RepositoryRecord]) -> list[ContextMessage]:
    context: list[ContextMessage] = []
    for record in records:
        role = record.get("role")
        content = record.get("content")
        if isinstance(role, str) and isinstance(content, str):
            context.append({"role": role, "content": content})
    return context


def _record_token_cost(record: RepositoryRecord) -> int:
    token_count = record.get("token_count")
    if (
        isinstance(token_count, int)
        and not isinstance(token_count, bool)
        and token_count > 0
    ):
        return token_count
    content = record.get("content")
    return _estimate_token_count(content if isinstance(content, str) else "")


def _record_sequence(record: RepositoryRecord) -> int:
    sequence = record.get("sequence_number")
    return (
        sequence if isinstance(sequence, int) and not isinstance(sequence, bool) else -1
    )


def _estimate_token_count(text: str) -> int:
    """Count exact tokens, retaining a minimum cost for empty legacy records."""
    return max(1, count_tokens(text))


def _truncate_to_budget(text: str, max_tokens: int) -> str:
    return truncate_to_token_budget(text, max_tokens)


def _build_cumulative_summary(
    previous: ConversationSummary | None, messages: Sequence[Message]
) -> str:
    parts: list[str] = []
    if previous is not None and previous.summary_text.strip():
        parts.append(previous.summary_text.strip())

    for message in messages:
        role = getattr(message.role, "value", str(message.role))
        prefix = {
            "user": "User",
            "assistant": "Assistant",
            "system": "System",
        }.get(role, "Message")
        normalized = " ".join(message.content.split())
        parts.append(f"{prefix}: {normalized[:300]}")

    return truncate_middle_to_token_budget(
        "\n".join(parts),
        settings.SUMMARY_MAX_TOKENS,
    )
