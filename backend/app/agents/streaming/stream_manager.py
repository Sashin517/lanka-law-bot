"""Mediator between LangGraph node activity and the event transport."""

from __future__ import annotations

from typing import Any

from app.agents.streaming.emitter_protocol import IStreamEmitter
from app.agents.streaming.event_bus import EventBus
from app.agents.streaming.event_bus import event_bus as default_event_bus
from app.agents.streaming.events import (
    StreamEvent,
    error_event,
    final_event,
    plan_generated,
    sources_found,
    step_detail,
    step_done,
    step_start,
    stream_start,
)


class ExecutionStreamManager(IStreamEmitter):
    """Concrete activity emitter bound to exactly one stream session."""

    __slots__ = ("_bus", "_event_counter", "_final_emitted", "_session_id")

    def __init__(self, session_id: str, bus: EventBus | None = None) -> None:
        if not session_id:
            raise ValueError("session_id must not be empty")
        self._session_id = session_id
        self._bus = bus or default_event_bus
        self._event_counter = 0
        self._final_emitted = False

    @property
    def session_id(self) -> str:
        """Identifier of the stream session owned by this manager."""

        return self._session_id

    @property
    def final_emitted(self) -> bool:
        """Return whether a final event was accepted by the session bus."""

        return self._final_emitted

    def _next_event_id(self) -> str:
        self._event_counter += 1
        return f"{self._session_id}:{self._event_counter}"

    def _emit(self, event: StreamEvent) -> bool:
        event.event_id = self._next_event_id()
        return self._bus.emit(self._session_id, event)

    def emit_stream_start(self, question: str, mode: str) -> None:
        """Emit the first lifecycle event for a graph execution."""

        self._emit(stream_start(self._session_id, question, mode))

    def emit_step_start(self, step_name: str, label: str) -> None:
        self._emit(step_start(self._session_id, step_name, label))

    def emit_step_detail(
        self,
        step_name: str,
        detail: str,
        **metadata: Any,
    ) -> None:
        self._emit(step_detail(self._session_id, step_name, detail, **metadata))

    def emit_step_done(
        self,
        step_name: str,
        label: str,
        **metadata: Any,
    ) -> None:
        self._emit(step_done(self._session_id, step_name, label, **metadata))

    def emit_sources_found(self, count: int, titles: list[str]) -> None:
        self._emit(sources_found(self._session_id, count, titles))

    def emit_plan(
        self,
        plan_type: str,
        steps: list[str],
        reasoning: str,
    ) -> None:
        self._emit(plan_generated(self._session_id, plan_type, steps, reasoning))

    def emit_final(self, response: dict[str, Any]) -> None:
        self._final_emitted = self._emit(final_event(self._session_id, response))

    def emit_error(self, error: str) -> None:
        self._emit(error_event(self._session_id, error))
