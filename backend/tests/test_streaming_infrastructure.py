"""Unit tests for the Phase 1 execution streaming infrastructure."""

from __future__ import annotations

import asyncio
import unittest

from app.agents.streaming import (
    EventBus,
    ExecutionStreamManager,
    NullEmitter,
    SessionChannel,
    get_emitter,
)
from app.agents.streaming.events import (
    StreamEventType,
    StreamStepStatus,
    step_start,
)


async def _collect(channel: SessionChannel):
    return [event async for event in channel]


class SessionChannelTests(unittest.IsolatedAsyncioTestCase):
    async def test_channel_preserves_fifo_order_until_closed(self) -> None:
        channel = SessionChannel("session-1", maxsize=3)
        first = step_start("session-1", "router", "Route")
        second = step_start("session-1", "research", "Research")

        self.assertTrue(channel.put(first))
        self.assertTrue(channel.put(second))
        channel.close()

        self.assertEqual(await _collect(channel), [first, second])
        self.assertTrue(channel.is_closed)
        self.assertFalse(channel.put(first))

    async def test_close_terminates_consumer_when_queue_is_full(self) -> None:
        channel = SessionChannel("session-1", maxsize=1)
        event = step_start("session-1", "router", "Route")
        channel.put(event)

        channel.close()

        self.assertEqual(
            await asyncio.wait_for(_collect(channel), timeout=0.25),
            [event],
        )

    async def test_put_drops_event_when_backpressure_limit_is_reached(self) -> None:
        channel = SessionChannel("session-1", maxsize=1)

        self.assertTrue(channel.put(step_start("session-1", "router", "Route")))
        self.assertFalse(channel.put(step_start("session-1", "research", "Research")))

    async def test_put_from_worker_thread_is_scheduled_on_owner_loop(self) -> None:
        channel = SessionChannel("session-1", maxsize=2)
        event = step_start("session-1", "retrieval", "Retrieving")

        self.assertTrue(await asyncio.to_thread(channel.put, event))
        channel.close()

        self.assertEqual(await _collect(channel), [event])

    def test_channel_validates_constructor_arguments(self) -> None:
        with self.assertRaises(ValueError):
            SessionChannel("")
        with self.assertRaises(ValueError):
            SessionChannel("session-1", maxsize=0)


class EventBusTests(unittest.IsolatedAsyncioTestCase):
    async def test_bus_routes_only_to_the_bound_session(self) -> None:
        bus = EventBus(channel_maxsize=4)
        channel = bus.create_channel("session-1")
        event = step_start("", "router", "Route")

        self.assertTrue(bus.emit("session-1", event))
        self.assertFalse(bus.emit("missing", event))
        self.assertEqual(event.session_id, "session-1")

        bus.close_channel("session-1")
        self.assertIsNone(bus.get_channel("session-1"))
        self.assertEqual(await _collect(channel), [event])

    async def test_duplicate_active_session_is_rejected(self) -> None:
        bus = EventBus()
        bus.create_channel("session-1")

        with self.assertRaises(ValueError):
            bus.create_channel("session-1")

        bus.close_channel("session-1")


class ExecutionStreamManagerTests(unittest.IsolatedAsyncioTestCase):
    async def test_manager_assigns_monotonic_ids_and_preserves_contract(self) -> None:
        bus = EventBus(channel_maxsize=16)
        channel = bus.create_channel("session-1")
        manager = ExecutionStreamManager("session-1", bus)

        manager.emit_stream_start("What is section 12?", "quick_qa")
        manager.emit_step_start("supervisor", "Analysing")
        manager.emit_step_detail("supervisor", "Fast path", route="quick_qa")
        manager.emit_step_done("supervisor", "Routed", route="quick_qa")
        manager.emit_sources_found(1, ["Rent Act"])
        manager.emit_plan("fast_path", ["quick_qa"], "Direct dispatch")
        manager.emit_final({"answer": "Answer"})
        manager.emit_error("failure")
        bus.close_channel("session-1")

        events = await _collect(channel)

        self.assertEqual(
            [event.event_id for event in events],
            [f"session-1:{index}" for index in range(1, 9)],
        )
        self.assertTrue(all(event.session_id == "session-1" for event in events))
        self.assertEqual(events[0].event_type, StreamEventType.STREAM_START)
        self.assertEqual(events[0].step_status, StreamStepStatus.RUNNING)
        self.assertEqual(events[-2].event_type, StreamEventType.FINAL)
        self.assertEqual(events[-2].final_response, {"answer": "Answer"})
        self.assertEqual(events[-1].event_type, StreamEventType.ERROR)

    def test_manager_requires_a_session_id(self) -> None:
        with self.assertRaises(ValueError):
            ExecutionStreamManager("")


class EmitterResolutionTests(unittest.TestCase):
    def test_missing_or_invalid_config_uses_null_emitter(self) -> None:
        self.assertIsInstance(get_emitter(None), NullEmitter)
        self.assertIsInstance(get_emitter({}), NullEmitter)
        self.assertIsInstance(
            get_emitter({"configurable": {"stream_emitter": object()}}),
            NullEmitter,
        )

    def test_manager_is_resolved_from_langgraph_config(self) -> None:
        manager = ExecutionStreamManager("session-1", EventBus())

        resolved = get_emitter({"configurable": {"stream_emitter": manager}})

        self.assertIs(resolved, manager)


if __name__ == "__main__":
    unittest.main()
