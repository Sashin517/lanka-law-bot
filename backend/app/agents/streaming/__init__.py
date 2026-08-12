"""Public streaming API used by LangGraph nodes and API adapters."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.agents.streaming.emitter_protocol import (
    FinalSuppressingEmitter,
    IStreamEmitter,
    NullEmitter,
)
from app.agents.streaming.event_bus import EventBus, SessionChannel, event_bus
from app.agents.streaming.stream_manager import ExecutionStreamManager

__all__ = [
    "EventBus",
    "ExecutionStreamManager",
    "FinalSuppressingEmitter",
    "IStreamEmitter",
    "NullEmitter",
    "SessionChannel",
    "event_bus",
    "get_emitter",
]

_null_emitter = NullEmitter()


def get_emitter(config: Mapping[str, Any] | None) -> IStreamEmitter:
    """Resolve the injected emitter or return the shared no-op strategy."""

    if not isinstance(config, Mapping):
        return _null_emitter

    configurable = config.get("configurable")
    if not isinstance(configurable, Mapping):
        return _null_emitter

    emitter = configurable.get("stream_emitter")
    if isinstance(emitter, IStreamEmitter):
        return emitter
    return _null_emitter
