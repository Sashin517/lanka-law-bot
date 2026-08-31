"""Unified PostgreSQL engines, sessions, metadata, and lifecycle helpers.

Existing document and drafting services use synchronous SQLAlchemy sessions
through psycopg. Conversation repositories use asynchronous sessions through
asyncpg. Both paths share one declarative metadata registry and database.
"""

from __future__ import annotations

import importlib
import ssl
import threading
from collections.abc import AsyncGenerator, Generator

from sqlalchemy import MetaData, create_engine, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

MODEL_MODULES: tuple[str, ...] = (
    "app.models.conversation",
    "app.models.document",
    "app.models.draft",
)


class Base(DeclarativeBase):
    """Shared declarative base for every PostgreSQL relational model."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def _create_async_engine() -> AsyncEngine:
    return create_async_engine(
        settings.postgres_url,
        pool_size=settings.POSTGRES_POOL_SIZE,
        max_overflow=settings.POSTGRES_MAX_OVERFLOW,
        pool_pre_ping=True,
        echo=False,
        connect_args=postgres_async_connect_args(),
    )


def postgres_async_connect_args() -> dict[str, object]:
    """Return a certificate-verifying SSL context for managed PostgreSQL."""

    sslmode = str(settings.postgres_url.query.get("ssl", "")).strip().lower()
    if sslmode in {"require", "verify-ca", "verify-full"}:
        return {"ssl": ssl.create_default_context()}
    return {}


postgres_engine = _create_async_engine()
sync_engine = create_engine(
    settings.postgres_sync_url,
    pool_size=settings.POSTGRES_POOL_SIZE,
    max_overflow=settings.POSTGRES_MAX_OVERFLOW,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=postgres_engine,
    class_=AsyncSession,
    autoflush=False,
    expire_on_commit=False,
)
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=sync_engine,
)

_initialization_lock = threading.Lock()
_sync_initialized = False


def _load_models() -> None:
    """Register all relational models on the shared metadata registry."""

    for model_module in MODEL_MODULES:
        importlib.import_module(model_module)


async def init_postgres() -> None:
    """Create the complete schema for explicit local/test bootstrap only.

    Production deployments must apply Alembic migrations instead of enabling
    automatic schema creation.
    """

    _load_models()
    async with postgres_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


def init_db() -> None:
    """Initialize or verify the synchronous PostgreSQL service path once."""

    global _sync_initialized
    if _sync_initialized:
        return

    _load_models()
    with _initialization_lock:
        if _sync_initialized:
            return
        if settings.POSTGRES_AUTO_CREATE_SCHEMA:
            Base.metadata.create_all(bind=sync_engine)
        else:
            with sync_engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        _sync_initialized = True


async def check_postgres_connection() -> None:
    """Fail fast when PostgreSQL is unreachable or credentials are invalid."""

    async with postgres_engine.connect() as connection:
        await connection.execute(text("SELECT 1"))


def get_db() -> Generator[Session, None, None]:
    """Yield one request-scoped synchronous PostgreSQL session."""

    session = SessionLocal()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield one request-scoped asynchronous PostgreSQL session."""

    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def close_postgres() -> None:
    """Release both asynchronous and synchronous PostgreSQL pools."""

    await postgres_engine.dispose()
    sync_engine.dispose()
