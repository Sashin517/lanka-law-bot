"""Focused tests for Phase 2 LangGraph node instrumentation."""

from __future__ import annotations

import inspect
import unittest
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

from app.agents.nodes.deep_research_node import deep_research_node
from app.agents.nodes.drafting_node import drafting_node
from app.agents.nodes.formatter_node import formatter_node
from app.agents.nodes.grounding_node import grounding_node
from app.agents.nodes.plan_executor_node import plan_executor_node
from app.agents.nodes.quick_qa_node import quick_qa_node
from app.agents.nodes.reasoning_node import reasoning_node
from app.agents.nodes.review_node import review_node
from app.agents.nodes.router_node import router_node
from app.agents.nodes.verify_node import verify_node
from app.agents.state import AgentState, ExecutionPlan, PlanStep
from app.agents.streaming import EventBus, ExecutionStreamManager
from app.agents.streaming.events import StreamEventType


class RecordingEmitter:
    """Minimal protocol implementation that records calls in order."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def _record(self, name: str, *args: Any, **kwargs: Any) -> None:
        self.calls.append((name, args, kwargs))

    def emit_step_start(self, step_name: str, label: str) -> None:
        self._record("step_start", step_name, label)

    def emit_step_detail(self, step_name: str, detail: str, **metadata: Any) -> None:
        self._record("step_detail", step_name, detail, **metadata)

    def emit_step_done(self, step_name: str, label: str, **metadata: Any) -> None:
        self._record("step_done", step_name, label, **metadata)

    def emit_sources_found(self, count: int, titles: list[str]) -> None:
        self._record("sources_found", count, titles)

    def emit_plan(self, plan_type: str, steps: list[str], reasoning: str) -> None:
        self._record("plan", plan_type, steps, reasoning)

    def emit_final(self, response: dict[str, Any]) -> None:
        self._record("final", response)

    def emit_error(self, error: str) -> None:
        self._record("error", error)


def _config(emitter: RecordingEmitter) -> dict[str, Any]:
    return {"configurable": {"stream_emitter": emitter}}


class NodeSignatureTests(unittest.TestCase):
    def test_all_graph_nodes_accept_optional_config(self) -> None:
        nodes = (
            router_node,
            quick_qa_node,
            deep_research_node,
            reasoning_node,
            drafting_node,
            review_node,
            verify_node,
            grounding_node,
            plan_executor_node,
            formatter_node,
        )

        for node in nodes:
            with self.subTest(node=node.__name__):
                parameter = inspect.signature(node).parameters.get("config")
                self.assertIsNotNone(parameter)
                self.assertIsNone(parameter.default)


class ControlNodeStreamingTests(unittest.IsolatedAsyncioTestCase):
    async def test_router_emits_fast_path_lifecycle(self) -> None:
        emitter = RecordingEmitter()

        await router_node(
            AgentState(question="What does section 12 say?", mode="quick_qa"),
            _config(emitter),
        )

        self.assertEqual(
            emitter.calls[0][0:2],
            ("step_start", ("supervisor", "Analysing your legal question")),
        )
        self.assertEqual(emitter.calls[-1][0], "step_done")
        self.assertEqual(emitter.calls[-1][2]["route"], "quick_qa")

    async def test_drafting_output_runs_grounding_judge_and_emits_score(self) -> None:
        emitter = RecordingEmitter()
        state = AgentState(
            mode="drafting",
            current_agent="drafting",
            markdown_content="Draft text",
            context_str="--- Legal Source [LAW-1] ---\nText: Supporting law.",
        )

        judge_result = {
            "is_grounded": True,
            "grounding_score": 0.92,
            "ungrounded_claims": [],
            "feedback": "",
        }
        judge = AsyncMock(return_value=judge_result)
        with patch(
            "app.agents.nodes.grounding_node._grounding_chain",
            new=SimpleNamespace(ainvoke=judge),
        ):
            await grounding_node(state, _config(emitter))

        self.assertEqual(emitter.calls[0][0], "step_start")
        self.assertEqual(emitter.calls[-1][0], "step_done")
        self.assertEqual(emitter.calls[-1][1][1], "Grounding passed")
        self.assertAlmostEqual(emitter.calls[-1][2]["grounding_score"], 0.92)
        self.assertNotIn("skipped", emitter.calls[-1][2])
        judge.assert_awaited_once()
        judge_input = judge.await_args.args[0]
        self.assertEqual(judge_input["response_mode"], "drafting")
        self.assertEqual(judge_input["claims"], "Draft text")

    async def test_ungrounded_drafting_output_routes_back_for_revision(self) -> None:
        emitter = RecordingEmitter()
        state = AgentState(
            mode="drafting",
            current_agent="drafting",
            markdown_content="Section 99 requires this clause.",
            context_str="--- Legal Source [LAW-1] ---\nText: No Section 99.",
        )
        judge = AsyncMock(
            return_value={
                "is_grounded": False,
                "grounding_score": 0.25,
                "ungrounded_claims": ["Section 99 requires this clause."],
                "feedback": "Remove the unsupported Section 99 assertion.",
            }
        )

        with patch(
            "app.agents.nodes.grounding_node._grounding_chain",
            new=SimpleNamespace(ainvoke=judge),
        ):
            command = await grounding_node(state, _config(emitter))

        self.assertEqual(command.goto, "drafting")
        self.assertEqual(command.update["retry_count"], 1)
        self.assertEqual(
            command.update["working_memory"]["ungrounded_claims"],
            ["Section 99 requires this clause."],
        )
        self.assertEqual(emitter.calls[-1][1][1], "Grounding failed")
        self.assertAlmostEqual(emitter.calls[-1][2]["grounding_score"], 0.25)

    async def test_plan_executor_reports_next_agent(self) -> None:
        emitter = RecordingEmitter()
        state = AgentState(
            execution_plan=ExecutionPlan(
                plan_type="planned",
                steps=[
                    PlanStep(agent="deep_research", purpose="Research"),
                    PlanStep(agent="reasoning", purpose="Analyse"),
                ],
            ),
            current_step_index=0,
        )

        await plan_executor_node(state, _config(emitter))

        self.assertEqual(emitter.calls[-1][0], "step_done")
        self.assertEqual(emitter.calls[-1][2]["next_agent"], "reasoning")

    async def test_formatter_emits_final_response_after_step_done(self) -> None:
        emitter = RecordingEmitter()

        result = await formatter_node(
            AgentState(question="Question", summary="Answer"),
            _config(emitter),
        )

        self.assertEqual(
            [call[0] for call in emitter.calls], ["step_start", "step_done", "final"]
        )
        self.assertEqual(
            emitter.calls[-1][1][0],
            result["final_response"],
        )

    async def test_nodes_remain_backward_compatible_without_config(self) -> None:
        result = await formatter_node(AgentState(summary="Answer"))

        self.assertEqual(result["final_response"]["answer"], "Answer")

    async def test_compiled_graph_propagates_emitter_through_config(self) -> None:
        from app.agents.graph import build_graph

        bus = EventBus(channel_maxsize=16)
        channel = bus.create_channel("graph-session")
        manager = ExecutionStreamManager("graph-session", bus)

        final_state = await build_graph().ainvoke(
            AgentState(
                question="Review this agreement",
                mode="review",
            ).model_dump(),
            config={"configurable": {"stream_emitter": manager}},
        )
        bus.close_channel("graph-session")
        events = [event async for event in channel]

        self.assertTrue(final_state["final_response"])
        self.assertEqual(events[-1].event_type, StreamEventType.FINAL)
        self.assertEqual(
            [event.step_name for event in events],
            [
                "supervisor",
                "supervisor",
                "supervisor",
                "formatter",
                "formatter",
                "formatter",
            ],
        )


if __name__ == "__main__":
    unittest.main()
