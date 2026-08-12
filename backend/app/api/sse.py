"""Reusable Server-Sent Events transport primitives for FastAPI routes.

The module owns wire serialization, proxy-safe response headers, heartbeat
comments, producer-task cancellation, and deterministic channel cleanup.
Business endpoints only construct request state and produce typed events.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass

from app.agents.streaming.event_bus import SessionChannel
from app.agents.streaming.events import StreamEvent
from fastapi.responses import StreamingResponse

DEFAULT_HEARTBEAT_SECONDS = 15.0
SSE_RESPONSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}

Producer = Callable[[], Awaitable[None]]
CloseChannel = Callable[[], None]


@dataclass(frozen=True, slots=True)
class SSEEventSerializer:
    """Serialize typed events into standards-compliant SSE frames."""

    include_event_id: bool = True

    def serialize(self, event: StreamEvent) -> str:
        """Return one complete SSE frame for ``event``."""

        lines: list[str] = []
        if self.include_event_id and event.event_id:
            lines.append(f"id: {self._single_line(event.event_id)}")
        lines.append(f"event: {self._single_line(event.event_type.value)}")
        # Pydantic's JSON serializer handles enums and prevents raw newlines
        # inside values from corrupting the SSE frame structure.
        lines.append(f"data: {event.model_dump_json()}")
        return "\n".join(lines) + "\n\n"

    @staticmethod
    def heartbeat() -> str:
        """Return an SSE comment that keeps idle proxies from timing out."""

        return ": heartbeat\n\n"

    @staticmethod
    def _single_line(value: str) -> str:
        return value.replace("\r", "").replace("\n", "")


async def stream_channel(
    *,
    channel: SessionChannel,
    producer: Producer,
    close_channel: CloseChannel,
    serializer: SSEEventSerializer | None = None,
    heartbeat_seconds: float = DEFAULT_HEARTBEAT_SECONDS,
) -> AsyncIterator[str]:
    """Run a producer and stream its channel with cancellation-safe cleanup."""

    if heartbeat_seconds <= 0:
        raise ValueError("heartbeat_seconds must be positive")

    event_serializer = serializer or SSEEventSerializer()

    async def produce_and_close() -> None:
        try:
            await producer()
        finally:
            close_channel()

    producer_task = asyncio.create_task(produce_and_close())
    event_iterator = aiter(channel)
    next_event_task: asyncio.Task[StreamEvent] | None = asyncio.create_task(
        anext(event_iterator)
    )

    try:
        while next_event_task is not None:
            done, _ = await asyncio.wait(
                {next_event_task},
                timeout=heartbeat_seconds,
            )
            if not done:
                yield event_serializer.heartbeat()
                continue

            try:
                event = next_event_task.result()
            except StopAsyncIteration:
                next_event_task = None
                break

            yield event_serializer.serialize(event)
            next_event_task = asyncio.create_task(anext(event_iterator))

        await producer_task
    except asyncio.CancelledError:
        producer_task.cancel()
        raise
    finally:
        close_channel()
        if next_event_task is not None and not next_event_task.done():
            next_event_task.cancel()
            with suppress(asyncio.CancelledError):
                await next_event_task
        if not producer_task.done():
            producer_task.cancel()
        with suppress(asyncio.CancelledError):
            await producer_task


def streaming_response(content: AsyncIterator[str]) -> StreamingResponse:
    """Build a consistently configured SSE response."""

    return StreamingResponse(
        content,
        media_type="text/event-stream",
        headers=SSE_RESPONSE_HEADERS,
    )
