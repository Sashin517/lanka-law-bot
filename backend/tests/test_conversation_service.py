from __future__ import annotations

import json
import unittest
from typing import Any
from unittest.mock import patch

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.database.postgres_session import ConversationBase
from app.models.conversation import AgentRun, Conversation, ConversationSummary, Message
from app.repositories.exceptions import (
    ConversationNotFoundError,
    InvalidCursorError,
    InvalidRepositoryDataError,
)
from app.repositories.pg_conversation_repo import PgConversationRepository
from app.repositories.pg_message_repo import PgMessageRepository
from app.repositories.unit_of_work import UnitOfWork
from app.services.conversation_service import ConversationService
from app.services.memory_service import ContextWindowBuilder, SlidingWindowStrategy
from app.utils.token_counter import count_tokens


class ConversationServiceIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as connection:
            await connection.run_sync(ConversationBase.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def test_conversation_repository_uses_ownership_and_keyset_pagination(
        self,
    ) -> None:
        async with self.sessions() as session:
            repository = PgConversationRepository(session)
            created = [
                await repository.create("user-1", f"Chat {number}", "quick_qa")
                for number in range(3)
            ]
            self.assertNotIn("user_id", created[0])
            await session.commit()

            first_page, cursor = await repository.list_by_user("user-1", limit=2)
            second_page, final_cursor = await repository.list_by_user(
                "user-1", cursor=cursor, limit=2
            )

            self.assertEqual(len(first_page), 2)
            self.assertIsNotNone(cursor)
            self.assertEqual(len(second_page), 1)
            self.assertIsNone(final_cursor)
            self.assertEqual(
                {item["id"] for item in first_page + second_page},
                {item["id"] for item in created},
            )
            self.assertIsNone(
                await repository.get_by_id(created[0]["id"], "different-user")
            )
            with self.assertRaises(ConversationNotFoundError):
                await repository.update_title(
                    created[0]["id"], "different-user", "Forbidden rename"
                )

            await repository.soft_delete(created[0]["id"], "user-1")
            await session.commit()
            self.assertIsNone(await repository.get_by_id(created[0]["id"], "user-1"))

    async def test_message_repository_persists_children_and_paginates(self) -> None:
        async with self.sessions() as session:
            conversations = PgConversationRepository(session)
            messages = PgMessageRepository(session)
            conversation = await conversations.create(
                "user-1", "Evidence question", "quick_qa"
            )
            first = await messages.create(
                conversation["id"],
                "user",
                "What is the applicable evidentiary rule?",
                attachments=[
                    {
                        "document_id": "document-1",
                        "filename": "evidence.pdf",
                        "status": "completed",
                    }
                ],
                token_count=9,
            )
            second = await messages.create(
                conversation["id"],
                "assistant",
                "The Evidence Ordinance applies.",
                citations=[
                    {
                        "citation_id": "[LAW-1]",
                        "title": "Evidence Ordinance",
                        "year": 1895,
                        "content": "Relevant source text",
                        "authoritative": True,
                    }
                ],
                token_count=8,
            )
            await session.commit()

            self.assertEqual(first["sequence_number"], 0)
            self.assertEqual(second["sequence_number"], 1)
            self.assertEqual(second["citations"][0]["excerpt"], "Relevant source text")
            self.assertEqual(first["attachments"][0]["document_id"], "document-1")

            page_one, cursor = await messages.list_by_conversation(
                conversation["id"], limit=1
            )
            page_two, final_cursor = await messages.list_by_conversation(
                conversation["id"], cursor=cursor, limit=1
            )
            self.assertEqual([item["sequence_number"] for item in page_one], [0])
            self.assertEqual([item["sequence_number"] for item in page_two], [1])
            self.assertIsNone(final_cursor)

            conversation_cursor = (await conversations.list_by_user("user-1", limit=1))[
                1
            ]
            if conversation_cursor is None:
                conversation_cursor = "not-a-message-cursor"
            with self.assertRaises(InvalidCursorError):
                await messages.list_by_conversation(
                    conversation["id"], cursor=conversation_cursor, limit=1
                )

    async def test_message_rejects_cross_conversation_agent_run(self) -> None:
        async with self.sessions() as session:
            conversations = PgConversationRepository(session)
            messages = PgMessageRepository(session)
            first = await conversations.create("user-1", "First", "quick_qa")
            second = await conversations.create("user-1", "Second", "quick_qa")
            session.add(AgentRun(id="run-1", conversation_id=second["id"]))

            with self.assertRaisesRegex(InvalidRepositoryDataError, "does not belong"):
                await messages.create(
                    first["id"],
                    "assistant",
                    "This link must be rejected.",
                    agent_run_id="run-1",
                )
            await session.rollback()

    async def test_service_updates_metadata_auto_titles_and_checks_ownership(
        self,
    ) -> None:
        async with self.sessions() as session:
            service = ConversationService(session)
            conversation = await service.create_conversation("user-1")
            first_question = (
                "Explain the rules governing electronic evidence in Sri Lankan "
                "civil proceedings"
            )

            with patch.object(settings, "AUTO_TITLE_AFTER_MESSAGES", 2):
                await service.add_user_message(
                    conversation["id"],
                    first_question,
                    user_id="user-1",
                    token_count=15,
                )
                await service.add_assistant_message(
                    conversation["id"],
                    "Electronic evidence is governed by the applicable statutes.",
                    user_id="user-1",
                    token_count=12,
                )

            updated = await service.get_conversation(conversation["id"], "user-1")
            self.assertIsNotNone(updated)
            assert updated is not None
            self.assertEqual(updated["message_count"], 2)
            self.assertEqual(
                updated["last_message_preview"],
                "Electronic evidence is governed by the applicable statutes.",
            )
            self.assertTrue(updated["title"].endswith("…"))
            self.assertLessEqual(len(updated["title"]), 61)

            with self.assertRaises(ConversationNotFoundError):
                await service.add_user_message(
                    conversation["id"], "Unauthorized", user_id="user-2"
                )
            self.assertEqual(
                await session.scalar(
                    select(func.count(Message.id)).where(
                        Message.conversation_id == conversation["id"]
                    )
                ),
                2,
            )

    async def test_invalid_child_data_rolls_back_the_whole_service_operation(
        self,
    ) -> None:
        async with self.sessions() as session:
            service = ConversationService(session)
            conversation = await service.create_conversation("user-1")

            with self.assertRaises(InvalidRepositoryDataError):
                await service.add_assistant_message(
                    conversation["id"],
                    "An answer that must not persist.",
                    user_id="user-1",
                    citations=[{"title": "Missing citation identifier"}],
                    agent_run={
                        "route": "quick_qa",
                        "duration_ms": 12,
                    },
                )

            self.assertEqual(
                await session.scalar(
                    select(func.count(Message.id)).where(
                        Message.conversation_id == conversation["id"]
                    )
                ),
                0,
            )
            self.assertEqual(
                await session.scalar(select(func.count(AgentRun.id))),
                0,
            )
            stored = await service.get_conversation(conversation["id"], "user-1")
            self.assertIsNotNone(stored)
            assert stored is not None
            self.assertEqual(stored["message_count"], 0)

    async def test_service_counts_tokens_and_atomically_links_agent_run(self) -> None:
        async with self.sessions() as session:
            service = ConversationService(session)
            conversation = await service.create_conversation("user-1")
            user_message = await service.add_user_message(
                conversation["id"],
                "Explain section 3.",
                user_id="user-1",
            )
            assistant_message = await service.add_assistant_message(
                conversation["id"],
                "Section 3 governs relevancy.",
                user_id="user-1",
                agent_run={
                    "route": "quick_qa",
                    "task_type": "legal_question",
                    "answer_mode": "direct",
                    "plan_type": "fast_path",
                    "steps_executed": [
                        {"agent": "quick_qa", "purpose": "Answer the question"}
                    ],
                    "total_steps": 1,
                    "completed_agents": ["quick_qa"],
                    "grounding_score": 0.9,
                    "duration_ms": 125,
                },
            )

            self.assertEqual(
                user_message["token_count"], count_tokens("Explain section 3.")
            )
            self.assertIsNotNone(assistant_message["agent_run_id"])
            run = await session.get(AgentRun, assistant_message["agent_run_id"])
            self.assertIsNotNone(run)
            assert run is not None
            self.assertEqual(run.conversation_id, conversation["id"])
            self.assertEqual(run.duration_ms, 125)
            self.assertEqual(json.loads(run.completed_agents), ["quick_qa"])

    async def test_memory_summary_is_atomic_and_context_keeps_recent_messages(
        self,
    ) -> None:
        async with self.sessions() as session:
            service = ConversationService(session)
            conversation = await service.create_conversation("user-1")

            with (
                patch.object(settings, "SUMMARY_TRIGGER_MESSAGE_COUNT", 4),
                patch.object(settings, "AUTO_TITLE_AFTER_MESSAGES", 2),
            ):
                await service.add_user_message(
                    conversation["id"], "Question one", user_id="user-1", token_count=3
                )
                await service.add_assistant_message(
                    conversation["id"], "Answer one", user_id="user-1", token_count=3
                )
                await service.add_user_message(
                    conversation["id"], "Question two", user_id="user-1", token_count=3
                )
                await service.add_assistant_message(
                    conversation["id"], "Answer two", user_id="user-1", token_count=3
                )

                summaries = list(
                    (
                        await session.scalars(
                            select(ConversationSummary).where(
                                ConversationSummary.conversation_id
                                == conversation["id"]
                            )
                        )
                    ).all()
                )
                self.assertEqual(len(summaries), 1)
                self.assertEqual(summaries[0].from_sequence, 0)
                self.assertEqual(summaries[0].to_sequence, 3)

                await service.add_user_message(
                    conversation["id"],
                    "Question three",
                    user_id="user-1",
                    token_count=3,
                )
                await service.add_assistant_message(
                    conversation["id"], "Answer three", user_id="user-1", token_count=3
                )
                context = await service.build_context_window(
                    conversation["id"], user_id="user-1", mode="deep_research"
                )

            self.assertEqual(context[0]["role"], "system")
            self.assertIn("Conversation summary", context[0]["content"])
            self.assertEqual(
                context[1:],
                [
                    {"role": "user", "content": "Question three"},
                    {"role": "assistant", "content": "Answer three"},
                ],
            )

    async def test_unit_of_work_rolls_back_uncommitted_context(self) -> None:
        async with self.sessions() as session:
            with self.assertRaisesRegex(RuntimeError, "force rollback"):
                async with UnitOfWork(session) as unit_of_work:
                    await unit_of_work.conversations.create(
                        "user-1", "Rollback me", "quick_qa"
                    )
                    raise RuntimeError("force rollback")

        async with self.sessions() as verification_session:
            count = await verification_session.scalar(
                select(func.count(Conversation.id))
            )
            self.assertEqual(count, 0)


class _RecentMessageStub:
    def __init__(self, records: list[dict[str, Any]]) -> None:
        self._records = records

    async def get_recent(
        self, conversation_id: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        del conversation_id
        return self._records[-limit:]


class ContextStrategyTests(unittest.IsolatedAsyncioTestCase):
    def test_mode_budgets_reserve_capacity_for_retrieval(self) -> None:
        expected = {
            "quick_qa": (0, 1200, 6),
            "deep_research": (800, 1600, 10),
            "reasoning": (800, 1600, 10),
            "drafting": (0, 800, 4),
            "review": (0, 1600, 8),
        }
        for mode, values in expected.items():
            with self.subTest(mode=mode):
                budget = ContextWindowBuilder.budget_for_mode(mode)
                self.assertEqual(
                    (
                        budget.summary_tokens,
                        budget.recent_tokens,
                        budget.recent_message_limit,
                    ),
                    values,
                )

    async def test_sliding_window_uses_largest_suffix_within_budget(self) -> None:
        strategy = SlidingWindowStrategy(window_size=3)
        records = [
            {"role": "user", "content": "old", "token_count": 3},
            {"role": "assistant", "content": "middle", "token_count": 4},
            {"role": "user", "content": "new", "token_count": 5},
        ]

        context = await strategy.build(
            "conversation-1",
            session=None,  # type: ignore[arg-type]
            messages=_RecentMessageStub(records),  # type: ignore[arg-type]
            max_tokens=9,
        )

        self.assertEqual(
            context,
            [
                {"role": "assistant", "content": "middle"},
                {"role": "user", "content": "new"},
            ],
        )

    async def test_sliding_window_can_exclude_current_persisted_turn(self) -> None:
        strategy = SlidingWindowStrategy(window_size=3)
        records = [
            {
                "id": "prior-message",
                "role": "assistant",
                "content": "Prior answer",
                "token_count": 3,
            },
            {
                "id": "current-message",
                "role": "user",
                "content": "Current question",
                "token_count": 3,
            },
        ]

        context = await strategy.build(
            "conversation-1",
            session=None,  # type: ignore[arg-type]
            messages=_RecentMessageStub(records),  # type: ignore[arg-type]
            max_tokens=20,
            exclude_message_id="current-message",
        )

        self.assertEqual(
            context,
            [{"role": "assistant", "content": "Prior answer"}],
        )
