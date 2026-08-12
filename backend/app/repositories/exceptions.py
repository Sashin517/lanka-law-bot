"""Persistence-layer exceptions with no dependency on HTTP concerns."""

from __future__ import annotations


class RepositoryError(Exception):
    """Base class for expected repository failures."""


class ConversationNotFoundError(RepositoryError, LookupError):
    """Raised when a conversation is absent, deleted, or not user-accessible."""


class InvalidCursorError(RepositoryError, ValueError):
    """Raised when an opaque pagination cursor is malformed or misapplied."""


class InvalidRepositoryDataError(RepositoryError, ValueError):
    """Raised when data cannot satisfy a persistence contract."""
