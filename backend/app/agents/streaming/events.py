"""SSE event schema — the canonical data contract between backend and frontend.

All events inherit from StreamEvent.  The discriminator field ``event_type``
maps to the SSE ``event:`` line, enabling typed dispatch on the client.

Event Lifecycle
---------------
stream_start → (step_start → step_detail* → step_done)* → final

Each step follows the state machine:
  pending → running → done | error | skipped
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class StreamEventType(str, Enum):
    """Discriminated union tag for all SSE event types."""

    STREAM_START = "stream_start"
    STEP_START = "step_start"
    STEP_DETAIL = "step_detail"
    STEP_DONE = "step_done"
    STEP_ERROR = "step_error"
    SOURCES_FOUND = "sources_found"
    PLAN_GENERATED = "plan_generated"
    FINAL = "final"
    ERROR = "error"
    HEARTBEAT = "heartbeat"


class StreamStepStatus(str, Enum):
    """State machine for a single execution step."""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"
    SKIPPED = "skipped"


class StreamEvent(BaseModel):
    """Base SSE event — serialised as one JSON line per ``data:`` frame."""

    event_type: StreamEventType
    session_id: str = ""
    event_id: str = ""
    timestamp: float = Field(default_factory=time.time)
    step_name: str = ""
    step_label: str = ""
    step_status: StreamStepStatus = StreamStepStatus.PENDING
    detail: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Only populated on event_type == FINAL
    final_response: dict[str, Any] | None = None


# ── Convenience factories ─────────────────────────────────────


def stream_start(session_id: str, question: str, mode: str) -> StreamEvent:
    return StreamEvent(
        event_type=StreamEventType.STREAM_START,
        session_id=session_id,
        step_name="stream",
        step_label="Starting execution",
        step_status=StreamStepStatus.RUNNING,
        metadata={"question": question[:200], "mode": mode},
    )


def step_start(session_id: str, step_name: str, label: str) -> StreamEvent:
    return StreamEvent(
        event_type=StreamEventType.STEP_START,
        session_id=session_id,
        step_name=step_name,
        step_label=label,
        step_status=StreamStepStatus.RUNNING,
    )


def step_detail(
    session_id: str, step_name: str, detail: str, **meta: Any
) -> StreamEvent:
    return StreamEvent(
        event_type=StreamEventType.STEP_DETAIL,
        session_id=session_id,
        step_name=step_name,
        detail=detail,
        step_status=StreamStepStatus.RUNNING,
        metadata=meta,
    )


def step_done(
    session_id: str, step_name: str, label: str, **meta: Any
) -> StreamEvent:
    return StreamEvent(
        event_type=StreamEventType.STEP_DONE,
        session_id=session_id,
        step_name=step_name,
        step_label=label,
        step_status=StreamStepStatus.DONE,
        metadata=meta,
    )


def sources_found(
    session_id: str, count: int, titles: list[str]
) -> StreamEvent:
    return StreamEvent(
        event_type=StreamEventType.SOURCES_FOUND,
        session_id=session_id,
        step_name="retrieval",
        step_label=f"Found {count} relevant legal authorities",
        step_status=StreamStepStatus.DONE,
        metadata={"count": count, "titles": titles[:8]},
    )


def plan_generated(
    session_id: str, plan_type: str, steps: list[str], reasoning: str
) -> StreamEvent:
    return StreamEvent(
        event_type=StreamEventType.PLAN_GENERATED,
        session_id=session_id,
        step_name="supervisor",
        step_label=f"Execution plan: {plan_type}",
        step_status=StreamStepStatus.DONE,
        metadata={
            "plan_type": plan_type,
            "planned_steps": steps,
            "reasoning": reasoning,
        },
    )


def final_event(session_id: str, response: dict) -> StreamEvent:
    return StreamEvent(
        event_type=StreamEventType.FINAL,
        session_id=session_id,
        step_name="formatter",
        step_label="Preparing final response",
        step_status=StreamStepStatus.DONE,
        final_response=response,
    )


def error_event(session_id: str, error: str) -> StreamEvent:
    return StreamEvent(
        event_type=StreamEventType.ERROR,
        session_id=session_id,
        step_name="stream",
        step_label="Error occurred",
        step_status=StreamStepStatus.ERROR,
        detail=error,
    )
