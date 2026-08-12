"""Unit tests for the reusable FastAPI SSE transport adapter."""

from __future__ import annotations

import asyncio
import json
import unittest

from app.agents.streaming import EventBus, ExecutionStreamManager
from app.agents.streaming.events import StreamEventType, step_start
from app.api.sse import SSEEventSerializer, stream_channel, streaming_response


class SSEEventSerializerTests(unittest.TestCase):
    def test_serializer_emits_id_type_and_single_json_data_line(self) -> None:
        event = step_start("session-1", "supervisor", "Analysing")
        event.event_id = "session-1:1"

        frame = SSEEventSerializer().serialize(event)

        self.assertTrue(frame.endswith("\n\n"))
        self.assertIn("id: session-1:1\n", frame)
        self.assertIn("event: step_start\n", frame)
        data_line = next(
            line.removeprefix("data: ")
            for line in frame.splitlines()
            if line.startswith("data: ")
        )
        self.assertEqual(json.loads(data_line)["step_name"], "supervisor")

    def test_serializer_removes_line_breaks_from_control_fields(self) -> None:
        event = step_start("session-1", "supervisor", "Analysing")
        event.event_id = "unsafe\r\nid"

        frame = SSEEventSerializer().serialize(event)

        self.assertIn("id: unsafeid\n", frame)


class SSEChannelLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_stream_runs_producer_serializes_events_and_cleans_up(self) -> None:
        bus = EventBus(channel_maxsize=8)
        channel = bus.create_channel("session-1")
        manager = ExecutionStreamManager("session-1", bus)
        close_calls = 0

        def close() -> None:
            nonlocal close_calls
            close_calls += 1
            bus.close_channel("session-1")

        async def produce() -> None:
            manager.emit_stream_start("Question", "quick_qa")
            manager.emit_final({"answer": "Answer"})

        frames = [
            frame
            async for frame in stream_channel(
                channel=channel,
                producer=produce,
                close_channel=close,
            )
        ]

        self.assertEqual(len(frames), 2)
        self.assertIn("event: stream_start", frames[0])
        self.assertIn("event: final", frames[1])
        self.assertGreaterEqual(close_calls, 1)
        self.assertIsNone(bus.get_channel("session-1"))

    async def test_stream_emits_heartbeat_while_producer_is_idle(self) -> None:
        bus = EventBus()
        channel = bus.create_channel("session-1")
        release = asyncio.Event()
        producer_stopped = asyncio.Event()

        async def produce() -> None:
            try:
                await release.wait()
            finally:
                producer_stopped.set()

        generator = stream_channel(
            channel=channel,
            producer=produce,
            close_channel=lambda: bus.close_channel("session-1"),
            heartbeat_seconds=0.01,
        )

        self.assertEqual(await anext(generator), ": heartbeat\n\n")
        await generator.aclose()
        await asyncio.wait_for(producer_stopped.wait(), timeout=0.25)
        self.assertIsNone(bus.get_channel("session-1"))

    def test_streaming_response_sets_proxy_safe_headers(self) -> None:
        async def content():
            if False:
                yield ""

        response = streaming_response(content())

        self.assertTrue(response.media_type.startswith("text/event-stream"))
        self.assertEqual(response.headers["x-accel-buffering"], "no")
        self.assertIn("no-cache", response.headers["cache-control"])


class TerminalBackpressureTests(unittest.IsolatedAsyncioTestCase):
    async def test_full_queue_preserves_final_event(self) -> None:
        bus = EventBus(channel_maxsize=1)
        channel = bus.create_channel("session-1")
        manager = ExecutionStreamManager("session-1", bus)
        manager.emit_step_start("worker", "Working")

        manager.emit_final({"answer": "Answer"})
        bus.close_channel("session-1")
        events = [event async for event in channel]

        self.assertEqual(
            [event.event_type for event in events], [StreamEventType.FINAL]
        )
        self.assertTrue(manager.final_emitted)

    async def test_terminal_event_replaces_oldest_event_before_close(self) -> None:
        bus = EventBus(channel_maxsize=1)
        channel = bus.create_channel("session-1")
        manager = ExecutionStreamManager("session-1", bus)
        manager.emit_step_start("worker", "Working")
        manager.emit_final({"answer": "Answer"})

        event = await anext(aiter(channel))
        bus.close_channel("session-1")

        self.assertEqual(event.event_type, StreamEventType.FINAL)


if __name__ == "__main__":
    unittest.main()
