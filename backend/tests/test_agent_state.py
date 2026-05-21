"""Unit tests for the AgentState schema and supporting data models.

Validates field defaults, serialization, and model integrity.
"""

from __future__ import annotations

import unittest

from app.agents.state import (
    AgentState,
    CitedClaim,
    GroundingResult,
    SourceChunk,
)


class TestSourceChunk(unittest.TestCase):
    """Validate SourceChunk defaults and serialisation."""

    def test_defaults(self):
        chunk = SourceChunk()
        self.assertEqual(chunk.citation_id, "")
        self.assertEqual(chunk.source_type, "legal_authority")
        self.assertIsNone(chunk.document_id)

    def test_user_document_type(self):
        chunk = SourceChunk(
            citation_id="[DOC-1]",
            content="Clause 5.1",
            title="Service Agreement",
            source_type="user_document",
            document_id="doc-abc",
            filename="contract.pdf",
        )
        self.assertEqual(chunk.source_type, "user_document")
        self.assertEqual(chunk.document_id, "doc-abc")


class TestCitedClaim(unittest.TestCase):
    """Validate CitedClaim construction."""

    def test_with_citations(self):
        claim = CitedClaim(
            statement="Section 12 prohibits eviction.",
            citation_ids=["[LAW-1]", "[LAW-2]"],
        )
        self.assertEqual(len(claim.citation_ids), 2)
        self.assertTrue(claim.is_grounded)

    def test_empty_citations_default(self):
        claim = CitedClaim(statement="A statement.")
        self.assertEqual(claim.citation_ids, [])


class TestGroundingResult(unittest.TestCase):
    """Validate GroundingResult defaults."""

    def test_defaults_not_grounded(self):
        result = GroundingResult()
        self.assertFalse(result.is_grounded)
        self.assertEqual(result.grounding_score, 0.0)
        self.assertEqual(result.ungrounded_claims, [])

    def test_grounded_result(self):
        result = GroundingResult(
            is_grounded=True,
            grounding_score=0.95,
        )
        self.assertTrue(result.is_grounded)
        self.assertGreater(result.grounding_score, 0.9)


class TestAgentState(unittest.TestCase):
    """Validate AgentState construction and defaults."""

    def test_minimal_state(self):
        state = AgentState(question="What is Section 12?")
        self.assertEqual(state.question, "What is Section 12?")
        self.assertEqual(state.document_ids, [])
        self.assertEqual(state.route, "")
        self.assertTrue(state.use_legal_corpus)
        self.assertFalse(state.use_user_documents)
        self.assertEqual(state.retry_count, 0)
        self.assertEqual(state.max_retries, 2)

    def test_state_with_documents(self):
        state = AgentState(
            question="Review this contract.",
            document_ids=["doc-1", "doc-2"],
            matter_id="matter-abc",
        )
        self.assertEqual(len(state.document_ids), 2)
        self.assertEqual(state.matter_id, "matter-abc")

    def test_serialization_roundtrip(self):
        """State can be serialised to dict and back (required by LangGraph)."""
        state = AgentState(
            question="Test query",
            route="quick_qa",
            analysis=[
                CitedClaim(statement="Claim 1", citation_ids=["[LAW-1]"]),
            ],
            grounding=GroundingResult(is_grounded=True, grounding_score=0.9),
        )
        data = state.model_dump()
        restored = AgentState(**data)
        self.assertEqual(restored.question, "Test query")
        self.assertEqual(restored.route, "quick_qa")
        self.assertEqual(len(restored.analysis), 1)
        self.assertTrue(restored.grounding.is_grounded)

    def test_default_disclaimer_present(self):
        state = AgentState()
        self.assertIn("research purposes only", state.disclaimer)


if __name__ == "__main__":
    unittest.main()
