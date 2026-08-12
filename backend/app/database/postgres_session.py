"""Async PostgreSQL infrastructure for research-chat persistence.

This module deliberately runs alongside :mod:`app.database.session`, which
continues to own the existing SQLite document and drafting metadata.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import MetaData, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class ConversationBase(DeclarativeBase):
    """Declarative base isolated from the legacy SQLite metadata models."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def _create_engine() -> AsyncEngine:
    return create_async_engine(
        settings.postgres_url,
        pool_size=settings.POSTGRES_POOL_SIZE,
        max_overflow=settings.POSTGRES_MAX_OVERFLOW,
        pool_pre_ping=True,
        echo=False,
    )


postgres_engine = _create_engine()

AsyncSessionLocal = async_sessionmaker(
    bind=postgres_engine,
    class_=AsyncSession,
    autoflush=False,
    expire_on_commit=False,
)


async def init_postgres() -> None:
    """Create conversation tables for local bootstrap and isolated tests.

    Production deployments should apply ``alembic upgrade head`` instead, so
    every schema change is versioned and reversible.
    """
    import app.models.conversation  # noqa: F401

    async with postgres_engine.begin() as connection:
        await connection.run_sync(ConversationBase.metadata.create_all)


async def check_postgres_connection() -> None:
    """Fail fast when PostgreSQL is unreachable or credentials are invalid."""
    async with postgres_engine.connect() as connection:
        await connection.execute(text("SELECT 1"))


async def close_postgres() -> None:
    """Release all pooled PostgreSQL connections during application shutdown."""
    await postgres_engine.dispose()


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield one request-scoped session and roll back failed transactions."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
