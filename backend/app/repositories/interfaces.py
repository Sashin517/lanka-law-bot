"""Abstract data-access contracts for persistent conversations.

Services depend on these interfaces rather than SQLAlchemy implementations,
which keeps business logic testable and follows dependency inversion.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from types import TracebackType
from typing import Any, Self

RepositoryRecord = dict[str, Any]


class ConversationRepositoryInterface(ABC):
    """Data-access contract for the Conversation aggregate root."""

    @abstractmethod
    async def create(
        self, user_id: str, title: str, query_mode: str
    ) -> RepositoryRecord: ...

    @abstractmethod
    async def get_by_id(
        self, conversation_id: str, user_id: str
    ) -> RepositoryRecord | None: ...

    @abstractmethod
    async def list_by_user(
        self,
        user_id: str,
        *,
        cursor: str | None = None,
        limit: int = 30,
        status: str = "active",
    ) -> tuple[list[RepositoryRecord], str | None]: ...

    @abstractmethod
    async def update_title(
        self, conversation_id: str, user_id: str, title: str
    ) -> None: ...

    @abstractmethod
    async def update_metadata(
        self,
        conversation_id: str,
        *,
        message_count: int | None = None,
        last_message_preview: str | None = None,
    ) -> None: ...

    @abstractmethod
    async def soft_delete(self, conversation_id: str, user_id: str) -> None: ...


class MessageRepositoryInterface(ABC):
    """Data-access contract for ordered messages and their child records."""

    @abstractmethod
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
    ) -> RepositoryRecord: ...

    @abstractmethod
    async def list_by_conversation(
        self,
        conversation_id: str,
        *,
        cursor: str | None = None,
        limit: int = 50,
        order: str = "asc",
    ) -> tuple[list[RepositoryRecord], str | None]: ...

    @abstractmethod
    async def get_recent(
        self, conversation_id: str, limit: int = 10
    ) -> list[RepositoryRecord]: ...

    @abstractmethod
    async def count_by_conversation(self, conversation_id: str) -> int: ...


class AgentRunRepositoryInterface(ABC):
    """Data-access contract for auditable agent execution metadata."""

    @abstractmethod
    async def create(
        self,
        conversation_id: str,
        *,
        route: str | None = None,
        task_type: str | None = None,
        answer_mode: str | None = None,
        plan_type: str | None = None,
        steps_executed: Sequence[Mapping[str, Any]] | None = None,
        total_steps: int = 0,
        planning_reasoning: str = "",
        completed_agents: Sequence[str] | None = None,
        grounding_score: float = 0.0,
        duration_ms: int = 0,
    ) -> RepositoryRecord: ...


class UnitOfWorkInterface(ABC):
    """Atomic transaction boundary spanning conversation repositories."""

    conversations: ConversationRepositoryInterface
    messages: MessageRepositoryInterface
    agent_runs: AgentRunRepositoryInterface

    @abstractmethod
    async def __aenter__(self) -> Self: ...

    @abstractmethod
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    @abstractmethod
    async def commit(self) -> None: ...

    @abstractmethod
    async def rollback(self) -> None: ...
