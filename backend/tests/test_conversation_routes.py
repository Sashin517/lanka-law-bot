from __future__ import annotations

import json
import unittest
from copy import deepcopy
from typing import Any
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.endpoints import conversation_routes
from app.auth.firebase_auth import get_current_user_id
from app.repositories.exceptions import ConversationNotFoundError, InvalidCursorError

_NOW = "2026-08-12T08:30:00+00:00"


def _conversation_record() -> dict[str, Any]:
    return {
        "id": "conversation-1",
        "title": "New Chat",
        "query_mode": "quick_qa",
        "status": "active",
        "message_count": 0,
        "last_message_preview": "",
        "created_at": _NOW,
        "updated_at": _NOW,
    }


def _message_record(
    message_id: str,
    role: str,
    content: str,
    sequence_number: int,
) -> dict[str, Any]:
    return {
        "id": message_id,
        "role": role,
        "content": content,
        "markdown_content": None,
        "confidence": None,
        "disclaimer": None,
        "sequence_number": sequence_number,
        "query_mode": "quick_qa" if role == "user" else None,
        "citations": [],
        "attachments": [],
        "created_at": _NOW,
    }


class _FakeConversationService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.failure: Exception | None = None
        self.assistant_was_saved = False

    async def create_conversation(self, **kwargs: Any) -> dict[str, Any]:
        self._record("create_conversation", kwargs)
        self._raise_if_configured()
        record = _conversation_record()
        record["title"] = kwargs["title"]
        record["query_mode"] = kwargs["query_mode"]
        return record

    async def list_conversations(
        self, **kwargs: Any
    ) -> tuple[list[dict[str, Any]], str | None]:
        self._record("list_conversations", kwargs)
        self._raise_if_configured()
        return [_conversation_record()], "next-page"

    async def get_conversation(
        self, conversation_id: str, user_id: str
    ) -> dict[str, Any] | None:
        self._record(
            "get_conversation",
            {"conversation_id": conversation_id, "user_id": user_id},
        )
        self._raise_if_configured()
        return _conversation_record()

    async def get_messages(
        self, conversation_id: str, **kwargs: Any
    ) -> tuple[list[dict[str, Any]], str | None]:
        self._record("get_messages", {"conversation_id": conversation_id, **kwargs})
        self._raise_if_configured()
        return [], None

    async def rename_conversation(
        self, conversation_id: str, user_id: str, title: str
    ) -> None:
        self._record(
            "rename_conversation",
            {
                "conversation_id": conversation_id,
                "user_id": user_id,
                "title": title,
            },
        )
        self._raise_if_configured()

    async def delete_conversation(self, conversation_id: str, user_id: str) -> None:
        self._record(
            "delete_conversation",
            {"conversation_id": conversation_id, "user_id": user_id},
        )
        self._raise_if_configured()

    async def add_user_message(self, **kwargs: Any) -> dict[str, Any]:
        self._record("add_user_message", kwargs)
        self._raise_if_configured()
        record = _message_record("user-message-1", "user", kwargs["content"], 0)
        record["attachments"] = deepcopy(kwargs["attachments"])
        return record

    async def build_context_window(
        self, conversation_id: str, **kwargs: Any
    ) -> list[dict[str, str]]:
        self._record(
            "build_context_window", {"conversation_id": conversation_id, **kwargs}
        )
        self._raise_if_configured()
        return [{"role": "assistant", "content": "Earlier response"}]

    async def add_assistant_message(self, **kwargs: Any) -> dict[str, Any]:
        self._record("add_assistant_message", kwargs)
        self._raise_if_configured()
        self.assistant_was_saved = True
        record = _message_record(
            "assistant-message-1", "assistant", kwargs["content"], 1
        )
        record["markdown_content"] = kwargs["markdown_content"]
        record["confidence"] = kwargs["confidence"]
        record["disclaimer"] = kwargs["disclaimer"]
        record["citations"] = deepcopy(kwargs["citations"])
        return record

    def _record(self, name: str, arguments: dict[str, Any]) -> None:
        self.calls.append((name, deepcopy(arguments)))

    def _raise_if_configured(self) -> None:
        if self.failure is not None:
            raise self.failure


class _FakeGraph:
    def __init__(self, *, failure: Exception | None = None) -> None:
        self.failure = failure
        self.states: list[dict[str, Any]] = []

    async def ainvoke(
        self,
        state: dict[str, Any],
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.states.append(deepcopy(state))
        if self.failure is not None:
            raise self.failure
        if config is not None:
            emitter = config["configurable"]["stream_emitter"]
            emitter.emit_step_start("quick_qa", "Researching legal authorities")
            emitter.emit_step_detail(
                "quick_qa",
                "Reviewing the conversation context",
            )
            emitter.emit_step_done("quick_qa", "Legal research complete")
            # The conversation adapter must suppress this internal graph result
            # and own the one public final event after both turns are persisted.
            emitter.emit_final({"answer": "internal graph response"})
        return {
            **state,
            "final_response": {
                "answer": "Section 3 governs the issue.",
                "markdown_content": "**Section 3** governs the issue.",
                "confidence": "high",
                "disclaimer": "Research information only.",
                "sources": [
                    {
                        "citation_id": "[LAW-1]",
                        "title": "Evidence Ordinance",
                        "year": 1895,
                        "content": "Section 3 text",
                    }
                ],
                "grounding_score": 0.92,
                "route": {
                    "route": "quick_qa",
                    "task_type": "legal_question",
                    "answer_mode": "direct",
                },
                "execution_trace": {
                    "plan_type": "fast_path",
                    "steps_executed": [
                        {"agent": "quick_qa", "purpose": "Answer directly"}
                    ],
                    "total_steps": 1,
                    "planning_reasoning": "Simple lookup.",
                    "completed_agents": ["quick_qa"],
                },
            },
        }


class ConversationRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = _FakeConversationService()
        self.graph = _FakeGraph()
        app = FastAPI()
        app.include_router(
            conversation_routes.router,
            prefix="/api/conversations",
        )
        app.dependency_overrides[get_current_user_id] = lambda: "firebase-user-1"
        app.dependency_overrides[conversation_routes.get_conversation_service] = (
            lambda: self.service
        )
        app.dependency_overrides[conversation_routes.get_conversation_graph] = lambda: (
            self.graph
        )
        self.app = app
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()

    def test_openapi_marks_every_conversation_operation_as_bearer_protected(
        self,
    ) -> None:
        paths = self.app.openapi()["paths"]
        for path, operations in paths.items():
            if not path.startswith("/api/conversations"):
                continue
            for method, operation in operations.items():
                with self.subTest(path=path, method=method):
                    self.assertEqual(operation["security"], [{"HTTPBearer": []}])

    def test_create_uses_authenticated_user_and_normalized_contract(self) -> None:
        response = self.client.post(
            "/api/conversations",
            json={"title": "  Contract   research  ", "query_mode": "reasoning"},
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["title"], "Contract research")
        self.assertNotIn("user_id", response.json())
        _, arguments = self.service.calls[0]
        self.assertEqual(arguments["user_id"], "firebase-user-1")
        self.assertEqual(arguments["query_mode"], "reasoning")

    def test_request_validation_rejects_unknown_and_duplicate_input(self) -> None:
        unknown = self.client.post(
            "/api/conversations",
            json={"title": "Research", "unexpected": True},
        )
        duplicate = self.client.post(
            "/api/conversations/conversation-1/messages",
            json={"content": "Question", "document_ids": ["doc-1", "doc-1"]},
        )

        self.assertEqual(unknown.status_code, 422)
        self.assertEqual(duplicate.status_code, 422)
        self.assertEqual(self.service.calls, [])

    def test_list_and_detail_return_typed_pagination_contracts(self) -> None:
        listing = self.client.get("/api/conversations?limit=10")
        detail = self.client.get("/api/conversations/conversation-1")

        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()["next_cursor"], "next-page")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["messages"]["messages"], [])
        self.assertNotIn("user_id", detail.json())

    def test_rename_delete_and_message_listing_keep_user_scope(self) -> None:
        renamed = self.client.patch(
            "/api/conversations/conversation-1/title",
            json={"title": "  Updated   research  "},
        )
        messages = self.client.get(
            "/api/conversations/conversation-1/messages?cursor=page-1&limit=25"
        )
        deleted = self.client.delete("/api/conversations/conversation-1")

        self.assertEqual(renamed.json(), {"status": "ok"})
        self.assertEqual(messages.json(), {"messages": [], "next_cursor": None})
        self.assertEqual(deleted.json(), {"status": "ok"})

        call_map = dict(self.service.calls)
        self.assertEqual(call_map["rename_conversation"]["title"], "Updated research")
        self.assertEqual(call_map["rename_conversation"]["user_id"], "firebase-user-1")
        self.assertEqual(call_map["get_messages"]["cursor"], "page-1")
        self.assertEqual(call_map["get_messages"]["limit"], 25)
        self.assertEqual(call_map["get_messages"]["user_id"], "firebase-user-1")
        self.assertEqual(call_map["delete_conversation"]["user_id"], "firebase-user-1")

    def test_expected_service_errors_have_stable_http_mappings(self) -> None:
        self.service.failure = ConversationNotFoundError("private")
        not_found = self.client.get("/api/conversations/private-conversation")
        self.assertEqual(not_found.status_code, 404)
        self.assertEqual(not_found.json()["detail"], "Conversation not found.")

        self.service.failure = InvalidCursorError("Cursor is invalid.")
        invalid_cursor = self.client.get("/api/conversations?cursor=invalid")
        self.assertEqual(invalid_cursor.status_code, 400)
        self.assertEqual(invalid_cursor.json()["detail"], "Cursor is invalid.")

    def test_send_persists_both_turns_and_passes_only_prior_context(self) -> None:
        response = self.client.post(
            "/api/conversations/conversation-1/messages",
            json={
                "content": "What does section 3 provide?",
                "query_mode": "quick_qa",
                "document_ids": ["doc-1"],
                "attachments": [
                    {
                        "document_id": "doc-1",
                        "filename": "evidence.pdf",
                        "status": "completed",
                    }
                ],
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["user_message"]["id"], "user-message-1")
        self.assertEqual(
            payload["assistant_message"]["content"],
            "Section 3 governs the issue.",
        )
        call_map = dict(self.service.calls)
        self.assertEqual(call_map["add_user_message"]["user_id"], "firebase-user-1")
        self.assertEqual(
            call_map["build_context_window"]["exclude_message_id"],
            "user-message-1",
        )
        self.assertEqual(
            call_map["add_assistant_message"]["citations"][0]["citation_id"],
            "[LAW-1]",
        )
        run = call_map["add_assistant_message"]["agent_run"]
        self.assertEqual(run["route"], "quick_qa")
        self.assertEqual(run["plan_type"], "fast_path")
        self.assertEqual(run["completed_agents"], ["quick_qa"])
        self.assertGreaterEqual(run["duration_ms"], 0)
        state = self.graph.states[0]
        self.assertEqual(state["question"], "What does section 3 provide?")
        self.assertEqual(state["document_ids"], ["doc-1"])
        self.assertEqual(
            state["working_memory"]["conversation_context"],
            [{"role": "assistant", "content": "Earlier response"}],
        )

    def test_graph_failure_preserves_user_turn_but_not_assistant_turn(self) -> None:
        failing_graph = _FakeGraph(failure=RuntimeError("provider unavailable"))
        self.app.dependency_overrides[conversation_routes.get_conversation_graph] = (
            lambda: failing_graph
        )

        response = self.client.post(
            "/api/conversations/conversation-1/messages",
            json={"content": "A question"},
        )

        self.assertEqual(response.status_code, 502)
        self.assertIn("message was saved", response.json()["detail"])
        self.assertFalse(self.service.assistant_was_saved)
        self.assertIn("add_user_message", [name for name, _ in self.service.calls])

    def test_streaming_send_emits_activity_and_one_persisted_final_response(
        self,
    ) -> None:
        with self.client.stream(
            "POST",
            "/api/conversations/conversation-1/messages/stream",
            json={
                "content": "What does section 3 provide?",
                "query_mode": "quick_qa",
                "document_ids": ["doc-1"],
            },
        ) as response:
            body = "\n".join(response.iter_lines())

        self.assertEqual(response.status_code, 200, body)
        self.assertTrue(response.headers["content-type"].startswith("text/event-stream"))
        events = _parse_sse_events(body)
        self.assertEqual(
            [event["event_type"] for event in events],
            ["stream_start", "step_start", "step_detail", "step_done", "final"],
        )
        final_events = [event for event in events if event["event_type"] == "final"]
        self.assertEqual(len(final_events), 1)
        final_response = final_events[0]["final_response"]
        self.assertEqual(final_response["user_message"]["id"], "user-message-1")
        self.assertEqual(
            final_response["assistant_message"]["id"],
            "assistant-message-1",
        )
        self.assertEqual(
            final_response["response"]["answer"],
            "Section 3 governs the issue.",
        )
        self.assertTrue(self.service.assistant_was_saved)

    def test_streaming_graph_failure_emits_terminal_error_without_assistant(
        self,
    ) -> None:
        self.app.dependency_overrides[conversation_routes.get_conversation_graph] = (
            lambda: _FakeGraph(failure=RuntimeError("private provider failure"))
        )

        with self.client.stream(
            "POST",
            "/api/conversations/conversation-1/messages/stream",
            json={"content": "A question"},
        ) as response:
            body = "\n".join(response.iter_lines())

        self.assertEqual(response.status_code, 200, body)
        events = _parse_sse_events(body)
        self.assertEqual(
            [event["event_type"] for event in events],
            ["stream_start", "error"],
        )
        self.assertIn("message was saved", events[-1]["detail"])
        self.assertNotIn("private provider failure", events[-1]["detail"])
        self.assertFalse(self.service.assistant_was_saved)


class ConversationAuthenticationTests(unittest.TestCase):
    def test_conversation_routes_fail_closed_without_bearer_token(self) -> None:
        service = _FakeConversationService()
        app = FastAPI()
        app.include_router(
            conversation_routes.router,
            prefix="/api/conversations",
        )
        app.dependency_overrides[conversation_routes.get_conversation_service] = (
            lambda: service
        )
        app.dependency_overrides[conversation_routes.get_conversation_graph] = (
            _FakeGraph
        )

        with TestClient(app) as client:
            response = client.get("/api/conversations")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers["www-authenticate"], "Bearer")
        self.assertEqual(service.calls, [])

    def test_conversation_stream_fails_closed_before_starting_work(self) -> None:
        service = _FakeConversationService()
        app = FastAPI()
        app.include_router(
            conversation_routes.router,
            prefix="/api/conversations",
        )
        app.dependency_overrides[conversation_routes.get_conversation_service] = (
            lambda: service
        )
        app.dependency_overrides[conversation_routes.get_conversation_graph] = (
            _FakeGraph
        )

        with TestClient(app) as client:
            response = client.post(
                "/api/conversations/conversation-1/messages/stream",
                json={"content": "A question"},
            )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers["www-authenticate"], "Bearer")
        self.assertEqual(service.calls, [])


def _parse_sse_events(body: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for frame in body.replace("\r\n", "\n").split("\n\n"):
        data_lines = [
            line.removeprefix("data: ")
            for line in frame.splitlines()
            if line.startswith("data: ")
        ]
        if data_lines:
            events.append(json.loads("\n".join(data_lines)))
    return events


class ApplicationLifespanTests(unittest.IsolatedAsyncioTestCase):
    async def test_production_startup_checks_schema_and_closes_pool(self) -> None:
        import main

        with (
            patch.object(main.settings, "POSTGRES_AUTO_CREATE_SCHEMA", False),
            patch.object(main, "init_db") as init_sqlite,
            patch.object(
                main, "check_postgres_connection", new_callable=AsyncMock
            ) as check_postgres,
            patch.object(
                main, "init_postgres", new_callable=AsyncMock
            ) as create_schema,
            patch.object(main, "init_firebase_admin") as init_firebase,
            patch.object(
                main, "close_postgres", new_callable=AsyncMock
            ) as close_postgres,
        ):
            async with main.lifespan(main.app):
                init_sqlite.assert_called_once_with()
                check_postgres.assert_awaited_once_with()
                create_schema.assert_not_awaited()
                init_firebase.assert_called_once_with()

            close_postgres.assert_awaited_once_with()

    async def test_local_bootstrap_can_create_schema_explicitly(self) -> None:
        import main

        with (
            patch.object(main.settings, "POSTGRES_AUTO_CREATE_SCHEMA", True),
            patch.object(main, "init_db"),
            patch.object(
                main, "check_postgres_connection", new_callable=AsyncMock
            ) as check_postgres,
            patch.object(
                main, "init_postgres", new_callable=AsyncMock
            ) as create_schema,
            patch.object(main, "init_firebase_admin"),
            patch.object(main, "close_postgres", new_callable=AsyncMock),
        ):
            async with main.lifespan(main.app):
                create_schema.assert_awaited_once_with()
                check_postgres.assert_not_awaited()
