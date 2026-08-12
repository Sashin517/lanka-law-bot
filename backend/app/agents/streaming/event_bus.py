"""In-process asynchronous event bus for per-request activity streams.

Each streaming request owns one bounded :class:`SessionChannel`. Producers do
not wait for slow clients: non-terminal events are dropped when the bounded
queue is full and the incident is logged. Closing enqueues a sentinel when
capacity permits; a full channel terminates immediately after its pending
events are drained.

The bus is deliberately process-local. It coordinates a graph invocation and
its SSE response within one worker; durable replay or cross-worker fan-out is
outside the Phase 1 contract.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import AsyncIterator

from app.agents.streaming.events import StreamEvent, StreamEventType

logger = logging.getLogger(__name__)

_STREAM_END = object()


class SessionChannel:
    """Bounded, single-consumer event channel for one stream session."""

    __slots__ = ("_closed", "_loop", "_owner_thread_id", "_queue", "session_id")

    def __init__(self, session_id: str, maxsize: int = 256) -> None:
        if not session_id:
            raise ValueError("session_id must not be empty")
        if maxsize < 1:
            raise ValueError("maxsize must be at least 1")

        self.session_id = session_id
        self._queue: asyncio.Queue[StreamEvent | object] = asyncio.Queue(
            maxsize=maxsize
        )
        self._closed = False
        try:
            self._loop: asyncio.AbstractEventLoop | None = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None
        self._owner_thread_id = threading.get_ident()

    @property
    def is_closed(self) -> bool:
        """Return whether the channel has been closed."""

        return self._closed

    def put(self, event: StreamEvent) -> bool:
        """Enqueue ``event`` without blocking.

        Returns ``True`` when accepted on the owner loop or safely scheduled
        from a worker thread. Returns ``False`` when a direct write is closed
        or backpressured. A scheduled worker write can still be dropped if the
        queue fills before its callback runs.
        """

        if self._closed:
            return False

        if self._loop is not None and threading.get_ident() != self._owner_thread_id:
            if self._loop.is_closed():
                return False
            self._loop.call_soon_threadsafe(self._put_nowait, event)
            return True

        return self._put_nowait(event)

    def _put_nowait(self, event: StreamEvent) -> bool:
        """Perform the queue mutation on the channel's owning event loop."""

        if self._closed:
            return False
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            if event.event_type in {StreamEventType.FINAL, StreamEventType.ERROR}:
                # Completion events are required for a usable transport. Evict
                # the oldest activity update while retaining bounded memory.
                self._queue.get_nowait()
                self._queue.put_nowait(event)
                logger.warning(
                    "SSE queue full for session '%s'; evicted oldest event "
                    "to preserve terminal event '%s'.",
                    self.session_id,
                    event.event_type.value,
                )
                return True
            logger.warning(
                "SSE queue full for session '%s'; dropping event '%s'.",
                self.session_id,
                event.event_type.value,
            )
            return False
        return True

    def close(self) -> None:
        """Idempotently signal end-of-stream, even when the queue is full."""

        if self._closed:
            return
        self._closed = True

        try:
            self._queue.put_nowait(_STREAM_END)
            return
        except asyncio.QueueFull:
            # Do not evict a pending event, especially FINAL or ERROR. The
            # iterator also observes the closed-and-empty state after draining
            # the full queue, so a sentinel is unnecessary in this branch.
            return

    async def __aiter__(self) -> AsyncIterator[StreamEvent]:
        """Yield events in FIFO order until :meth:`close` is called."""

        while True:
            if self._closed and self._queue.empty():
                return
            item = await self._queue.get()
            if item is _STREAM_END:
                return
            if isinstance(item, StreamEvent):
                yield item


class EventBus:
    """Registry and publisher for active per-session channels."""

    def __init__(self, *, channel_maxsize: int = 256) -> None:
        if channel_maxsize < 1:
            raise ValueError("channel_maxsize must be at least 1")
        self._channel_maxsize = channel_maxsize
        self._channels: dict[str, SessionChannel] = {}

    def create_channel(self, session_id: str) -> SessionChannel:
        """Create a channel, rejecting duplicate active session identifiers."""

        existing = self._channels.get(session_id)
        if existing is not None and not existing.is_closed:
            raise ValueError(f"An active SSE channel already exists for '{session_id}'")

        channel = SessionChannel(session_id, maxsize=self._channel_maxsize)
        self._channels[session_id] = channel
        logger.debug("SSE channel created: %s", session_id)
        return channel

    def get_channel(self, session_id: str) -> SessionChannel | None:
        """Return the active channel for ``session_id``, if any."""

        return self._channels.get(session_id)

    def emit(self, session_id: str, event: StreamEvent) -> bool:
        """Publish an event to a session, returning whether it was accepted."""

        channel = self._channels.get(session_id)
        if channel is None:
            logger.debug("Ignoring event for unknown SSE session: %s", session_id)
            return False

        event.session_id = session_id
        return channel.put(event)

    def close_channel(self, session_id: str) -> None:
        """Remove and close a session channel. Safe to call repeatedly."""

        channel = self._channels.pop(session_id, None)
        if channel is not None:
            channel.close()
            logger.debug("SSE channel closed: %s", session_id)


event_bus = EventBus()
