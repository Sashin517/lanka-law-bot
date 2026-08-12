"""Unit of Work coordinating atomic multi-repository transactions."""

from __future__ import annotations

from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.interfaces import UnitOfWorkInterface
from app.repositories.pg_agent_run_repo import PgAgentRunRepository
from app.repositories.pg_conversation_repo import PgConversationRepository
from app.repositories.pg_message_repo import PgMessageRepository


class UnitOfWork(UnitOfWorkInterface):
    """Expose repositories backed by one shared SQLAlchemy AsyncSession.

    The FastAPI session dependency owns session lifetime by default. Setting
    ``close_on_exit=True`` is available to non-request callers that transfer
    session ownership to the Unit of Work.
    """

    def __init__(self, session: AsyncSession, *, close_on_exit: bool = False) -> None:
        self._session = session
        self._close_on_exit = close_on_exit
        self._completed = False
        self.conversations = PgConversationRepository(session)
        self.messages = PgMessageRepository(session)
        self.agent_runs = PgAgentRunRepository(session)

    async def __aenter__(self) -> Self:
        self._completed = False
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if exc_type is not None or not self._completed:
            await self._session.rollback()
        if self._close_on_exit:
            await self._session.close()

    async def commit(self) -> None:
        try:
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        self._completed = True

    async def rollback(self) -> None:
        await self._session.rollback()
        self._completed = True
