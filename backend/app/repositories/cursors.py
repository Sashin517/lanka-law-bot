"""Opaque, versioned keyset-pagination cursor helpers."""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from typing import Any

from app.repositories.exceptions import InvalidCursorError

_CURSOR_VERSION = 1
_MAX_CURSOR_LENGTH = 2048


def encode_cursor(kind: str, values: Mapping[str, Any]) -> str:
    """Encode cursor values without exposing a public serialization contract."""
    payload = {"v": _CURSOR_VERSION, "kind": kind, "values": dict(values)}
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: str, *, expected_kind: str) -> dict[str, Any]:
    """Decode and validate a cursor for a specific repository query."""
    if not cursor or len(cursor) > _MAX_CURSOR_LENGTH:
        raise InvalidCursorError("Invalid pagination cursor.")

    try:
        padding = "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode((cursor + padding).encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise InvalidCursorError("Invalid pagination cursor.") from exc

    if not isinstance(payload, dict):
        raise InvalidCursorError("Invalid pagination cursor.")
    if payload.get("v") != _CURSOR_VERSION or payload.get("kind") != expected_kind:
        raise InvalidCursorError("Pagination cursor does not match this resource.")

    values = payload.get("values")
    if not isinstance(values, dict):
        raise InvalidCursorError("Invalid pagination cursor values.")
    return values
