"""Integration tests for the additive Phase 3 streaming endpoints."""

from __future__ import annotations

import json
import unittest
from unittest.mock import ANY, AsyncMock, patch

from app.api.api_routes import api_router
from app.api.endpoints.draft_stream_routes import edit_draft_stream
from app.api.endpoints.query_routes import search_law
from app.api.endpoints.stream_routes import search_law_stream
from app.schemas.requests import DraftEditRequest, LegalQuery, QueryMode
from app.schemas.responses import DraftEditResponse


def _event_payloads(chunks: list[str | bytes]) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for chunk in chunks:
        frame = chunk.decode() if isinstance(chunk, bytes) else chunk
        if frame.startswith(":"):
            continue
        event_type = ""
        payload: dict = {}
        for line in frame.splitlines():
            if line.startswith("event: "):
                event_type = line.removeprefix("event: ")
            elif line.startswith("data: "):
                payload = json.loads(line.removeprefix("data: "))
        events.append((event_type, payload))
    return events


async def _consume(response) -> list[tuple[str, dict]]:
    chunks = [chunk async for chunk in response.body_iterator]
    return _event_payloads(chunks)


class _EmittingGraph:
    def __init__(
        self,
        *,
        emit_final: bool = True,
        fail: bool = False,
        omit_final_response: bool = False,
    ) -> None:
        self.emit_final = emit_final
        self.fail = fail
        self.omit_final_response = omit_final_response
        self.state: dict | None = None

    async def ainvoke(self, state: dict, config: dict | None = None) -> dict:
        self.state = state
        if self.fail:
            raise RuntimeError("graph failed")
        final = {"answer": "Streamed answer", "sources": []}
        if config is not None:
            emitter = config["configurable"]["stream_emitter"]
            emitter.emit_step_start("worker", "Working")
            emitter.emit_step_done("worker", "Complete")
            if self.emit_final:
                emitter.emit_final(final)
        if self.omit_final_response:
            return {"summary": "Fallback answer", "confidence": "low"}
        return {"final_response": final}


def _draft_response(path: str) -> DraftEditResponse:
    return DraftEditResponse(
        edit_type="full_rewrite" if path == "heavy" else "replace",
        original_text="old",
        edited_text="new",
        markdown_content="new",
        edit_summary="Updated draft.",
        edit_path=path,
    )


class RouteRegistrationTests(unittest.TestCase):
    def test_streaming_routes_are_additive(self) -> None:
        paths = {route.path for route in api_router.routes}

        self.assertIn("/api/search", paths)
        self.assertIn("/api/search/stream", paths)
        self.assertIn("/api/draft/edit", paths)
        self.assertIn("/api/draft/edit/stream", paths)


class LegacyCompatibilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_existing_search_endpoint_retains_non_streaming_contract(
        self,
    ) -> None:
        graph = _EmittingGraph()

        with patch("app.api.endpoints.query_routes.get_graph", return_value=graph):
            response = await search_law(LegalQuery(question="Question"))

        self.assertEqual(response["answer"], "Streamed answer")


class SearchStreamTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_stream_runs_real_graph_on_offline_clarification_path(
        self,
    ) -> None:
        query = LegalQuery(
            question="Review this agreement",
            mode=QueryMode.REVIEW,
        )

        events = await _consume(await search_law_stream(query))

        self.assertEqual(events[-1][0], "final")
        self.assertIn(
            "upload or attach",
            events[-1][1]["final_response"]["answer"].lower(),
        )

    async def test_search_stream_emits_activity_and_exactly_one_final(self) -> None:
        graph = _EmittingGraph()
        query = LegalQuery(question="What is section 12?", mode=QueryMode.QUICK_QA)

        with patch("app.api.endpoints.stream_routes.get_graph", return_value=graph):
            events = await _consume(await search_law_stream(query))

        event_types = [event_type for event_type, _ in events]
        self.assertEqual(
            event_types,
            ["stream_start", "step_start", "step_done", "final"],
        )
        self.assertEqual(event_types.count("final"), 1)
        self.assertEqual(events[-1][1]["final_response"]["answer"], "Streamed answer")
        self.assertEqual(graph.state["mode"], "quick_qa")
        self.assertTrue(graph.state["session_id"])

    async def test_search_stream_falls_back_when_graph_does_not_emit_final(
        self,
    ) -> None:
        graph = _EmittingGraph(emit_final=False)

        with patch("app.api.endpoints.stream_routes.get_graph", return_value=graph):
            events = await _consume(
                await search_law_stream(LegalQuery(question="Question"))
            )

        self.assertEqual([kind for kind, _ in events].count("final"), 1)

    async def test_search_stream_converts_graph_failure_to_error_event(self) -> None:
        graph = _EmittingGraph(fail=True)

        with patch("app.api.endpoints.stream_routes.get_graph", return_value=graph):
            events = await _consume(
                await search_law_stream(LegalQuery(question="Question"))
            )

        self.assertEqual([kind for kind, _ in events], ["stream_start", "error"])
        self.assertEqual(events[-1][1]["detail"], "graph failed")

    async def test_search_stream_matches_legacy_fallback_response(self) -> None:
        graph = _EmittingGraph(emit_final=False, omit_final_response=True)

        with patch("app.api.endpoints.stream_routes.get_graph", return_value=graph):
            events = await _consume(
                await search_law_stream(LegalQuery(question="Question"))
            )

        final = events[-1][1]["final_response"]
        self.assertEqual(final["answer"], "Fallback answer")
        self.assertEqual(final["confidence"], "low")


class DraftEditStreamTests(unittest.IsolatedAsyncioTestCase):
    async def test_light_edit_uses_existing_service_and_emits_final(self) -> None:
        request = DraftEditRequest(
            draft_id="draft-1",
            instruction="Make this clearer",
            selected_text="old",
            current_content="old",
        )
        light = AsyncMock(return_value=_draft_response("light"))
        heavy = AsyncMock(return_value=_draft_response("heavy"))

        with (
            patch(
                "app.services.generation.draft_edit_service.process_light_edit",
                light,
            ),
            patch(
                "app.services.generation.draft_edit_service.process_heavy_edit",
                heavy,
            ),
        ):
            events = await _consume(await edit_draft_stream(request))

        light.assert_awaited_once_with(request, stream_emitter=ANY)
        heavy.assert_not_awaited()
        self.assertEqual(
            [kind for kind, _ in events],
            ["stream_start", "step_start", "step_done", "final"],
        )
        self.assertEqual(events[-1][1]["final_response"]["edit_path"], "light")

    async def test_heavy_instruction_uses_structural_edit_service(self) -> None:
        request = DraftEditRequest(
            draft_id="draft-1",
            instruction="Rewrite the entire document",
            current_content="old",
        )
        light = AsyncMock(return_value=_draft_response("light"))
        heavy = AsyncMock(return_value=_draft_response("heavy"))

        with (
            patch(
                "app.services.generation.draft_edit_service.process_light_edit",
                light,
            ),
            patch(
                "app.services.generation.draft_edit_service.process_heavy_edit",
                heavy,
            ),
        ):
            events = await _consume(await edit_draft_stream(request))

        heavy.assert_awaited_once_with(request, stream_emitter=ANY)
        light.assert_not_awaited()
        self.assertEqual(events[-1][1]["final_response"]["edit_path"], "heavy")


if __name__ == "__main__":
    unittest.main()
