from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from app.schemas.requests import DraftEditRequest
from app.schemas.responses import SourceReference
from app.services.generation import draft_edit_service
from app.services.generation.citation_verifier import CitationVerifier


class _FakeRetrieval:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def search(self, **kwargs):
        self.calls.append(kwargs)
        return ["retrieved"]


class _FakeAssembler:
    def assemble(self, **kwargs):
        assert kwargs == {
            "legal_results": ["retrieved"],
            "user_document_results": [],
        }
        return (
            "legal context",
            {
                "[LAW-1]": SourceReference(
                    citation_id="[LAW-1]",
                    title="Data Protection Act",
                    year=2022,
                )
            },
        )


class _FakeChain:
    def __init__(self, result: dict) -> None:
        self.result = result
        self.payload: dict | None = None

    async def ainvoke(self, payload: dict) -> dict:
        self.payload = payload
        return self.result


class _FakeGraph:
    def __init__(self, final_state: dict) -> None:
        self.final_state = final_state
        self.state: dict | None = None
        self.config: dict | None = None

    async def ainvoke(self, state: dict, config: dict | None = None) -> dict:
        self.state = state
        self.config = config
        if config is not None:
            emitter = config["configurable"]["stream_emitter"]
            emitter.emit_step_start("drafting", "Drafting")
            emitter.emit_final({"answer": "Internal graph response"})
        return self.final_state


class _RecordingEmitter:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def emit_step_start(self, *args, **kwargs) -> None:
        self.calls.append("step_start")

    def emit_step_detail(self, *args, **kwargs) -> None:
        self.calls.append("step_detail")

    def emit_step_done(self, *args, **kwargs) -> None:
        self.calls.append("step_done")

    def emit_sources_found(self, *args, **kwargs) -> None:
        self.calls.append("sources_found")

    def emit_plan(self, *args, **kwargs) -> None:
        self.calls.append("plan")

    def emit_final(self, *args, **kwargs) -> None:
        self.calls.append("final")

    def emit_error(self, *args, **kwargs) -> None:
        self.calls.append("error")


class TestLightDraftEdit(unittest.TestCase):
    def test_light_edit_retrieves_verifies_and_merges_replacement(self):
        retrieval = _FakeRetrieval()
        chain = _FakeChain(
            {
                "edit_type": "replace",
                "edited_text": "The Tenant shall pay promptly [LAW-1] [LAW-99].",
                "edit_summary": "Formalized the payment obligation.",
                "sources_used": ["[LAW-1]", "[LAW-99]"],
                "confidence": "high",
            }
        )
        request = DraftEditRequest(
            draft_id="draft-1",
            instruction="Make this more formal",
            selected_text="Tenant pays promptly.",
            selection_start=9,
            selection_end=30,
            current_content="Payment: Tenant pays promptly. End.",
        )

        with (
            patch.object(
                draft_edit_service,
                "_get_light_dependencies",
                return_value=(retrieval, _FakeAssembler(), CitationVerifier()),
            ),
            patch.object(draft_edit_service, "_get_edit_chain", return_value=chain),
        ):
            result = asyncio.run(draft_edit_service.process_light_edit(request))

        self.assertEqual(result.edit_path, "light")
        self.assertEqual(result.edit_type, "replace")
        self.assertIn("[LAW-1]", result.edited_text)
        self.assertNotIn("[LAW-99]", result.edited_text)
        self.assertEqual(len(result.sources), 1)
        self.assertEqual(
            result.markdown_content,
            "Payment: The Tenant shall pay promptly [LAW-1]. End.",
        )
        self.assertEqual(retrieval.calls[0]["top_k"], 5)
        self.assertTrue(retrieval.calls[0]["expand_parents"])
        self.assertIn("disable_bm25", retrieval.calls[0])
        self.assertEqual(chain.payload["selected_text"], "Tenant pays promptly.")

    def test_ambiguous_selection_is_rejected(self):
        request = DraftEditRequest(
            draft_id="draft-1",
            instruction="Improve this",
            selected_text="same",
            current_content="same and same",
        )
        with self.assertRaises(draft_edit_service.DraftEditConflictError):
            draft_edit_service._apply_local_edit(request, "better")


class TestHeavyDraftEdit(unittest.TestCase):
    def test_heavy_edit_injects_complete_revision_context(self):
        graph = _FakeGraph(
            {
                "final_response": {
                    "markdown_content": "# Revised Agreement\n\nRevised terms.",
                    "sources": [
                        {
                            "citation_id": "[LAW-1]",
                            "title": "Data Protection Act",
                            "year": 2022,
                        }
                    ],
                    "confidence": "high",
                    "change_summary": "Aligned the agreement with the Act.",
                    "execution_trace": {"plan_type": "planned"},
                }
            }
        )
        content = "A" * 3_500
        request = DraftEditRequest(
            draft_id="draft-2",
            instruction="Rewrite the entire document to comply with the Act",
            selected_text=None,
            current_content=content,
            document_ids=["doc-1"],
        )

        with patch.object(draft_edit_service, "get_graph", return_value=graph):
            result = asyncio.run(draft_edit_service.process_heavy_edit(request))

        self.assertEqual(result.edit_path, "heavy")
        self.assertEqual(result.edit_type, "full_rewrite")
        self.assertEqual(result.execution_trace, {"plan_type": "planned"})
        self.assertEqual(graph.state["mode"], "drafting")
        self.assertEqual(graph.state["document_ids"], ["doc-1"])
        memory = graph.state["working_memory"]
        self.assertTrue(memory["is_revision"])
        self.assertEqual(memory["existing_draft"], content)
        self.assertEqual(memory["revision_instruction"], request.instruction)
        self.assertLess(len(graph.state["question"]), len(content) + 500)

    def test_streaming_heavy_edit_forwards_activity_but_suppresses_child_final(self):
        graph = _FakeGraph(
            {
                "final_response": {
                    "markdown_content": "# Revised Agreement",
                    "sources": [],
                    "confidence": "high",
                }
            }
        )
        emitter = _RecordingEmitter()
        request = DraftEditRequest(
            draft_id="draft-2",
            instruction="Rewrite the entire document",
            current_content="Old agreement",
        )

        with patch.object(draft_edit_service, "get_graph", return_value=graph):
            result = asyncio.run(
                draft_edit_service.process_heavy_edit(
                    request,
                    stream_emitter=emitter,
                )
            )

        self.assertEqual(result.edit_path, "heavy")
        self.assertIsNotNone(graph.config)
        self.assertIn("step_start", emitter.calls)
        self.assertNotIn("final", emitter.calls)


if __name__ == "__main__":
    unittest.main()
