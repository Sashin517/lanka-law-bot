"""Unit tests for the graph builder and formatter node.

Tests graph compilation, node registration, and the formatter's
frontend-facing response structure.
"""

from __future__ import annotations

import asyncio
import unittest

from app.agents.nodes.formatter_node import formatter_node
from app.agents.state import (
    AgentState,
    GroundingResult,
    SourceChunk,
)


class TestGraphCompilation(unittest.TestCase):
    """Verify the graph compiles without errors."""

    def test_graph_compiles(self):
        """Graph should compile with all registered nodes."""
        from app.agents.graph import build_graph

        graph = build_graph()
        self.assertIsNotNone(graph)


class TestFormatterNode(unittest.TestCase):
    """Verify the formatter produces frontend-compatible output."""

    def _make_state(self, **overrides) -> AgentState:
        defaults = {
            "question": "What is Section 12?",
            "mode": "quick_qa",
            "route": "quick_qa",
            "task_type": "qa",
            "answer_mode": "direct_answer",
            "target_corpus": "both",
            "route_confidence": "high",
            "summary": "Section 12 prohibits eviction.",
            "markdown_content": "**Section 12** prohibits eviction.",
            "retrieved_sources": [
                SourceChunk(
                    citation_id="[LAW-1]",
                    content="Full text of section 12...",
                    title="Rent Act No. 7 of 1972",
                    section="Section 12",
                    year=1972,
                    excerpt="Section 12 prohibits...",
                ),
            ],
            "confidence": "high",
            "grounding": GroundingResult(
                is_grounded=True,
                grounding_score=0.95,
            ),
        }
        defaults.update(overrides)
        return AgentState(**defaults)

    def test_final_response_structure(self):
        """Formatter should produce all required response keys."""
        result = asyncio.run(formatter_node(self._make_state()))
        resp = result["final_response"]

        for key in (
            "route",
            "answer",
            "markdown_content",
            "sources",
            "confidence",
            "grounding_score",
            "disclaimer",
            "execution_trace",
        ):
            self.assertIn(key, resp)
        self.assertNotIn("results", resp)
        self.assertNotIn("analysis", resp)

    def test_sources_are_serialized(self):
        result = asyncio.run(formatter_node(self._make_state()))
        sources = result["final_response"]["sources"]

        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]["citation_id"], "[LAW-1]")
        self.assertIn("Rent Act", sources[0]["title"])

    def test_grounding_score_in_response(self):
        result = asyncio.run(formatter_node(self._make_state()))
        self.assertAlmostEqual(result["final_response"]["grounding_score"], 0.95)

    def test_empty_state_produces_valid_response(self):
        """Formatter should handle empty retrieval gracefully."""
        result = asyncio.run(
            formatter_node(
                self._make_state(
                    summary="No results found.",
                    markdown_content="",
                    retrieved_sources=[],
                    confidence="low",
                )
            )
        )
        resp = result["final_response"]

        self.assertEqual(resp["answer"], "No results found.")
        self.assertEqual(resp["sources"], [])
        self.assertEqual(resp["route"]["route"], "quick_qa")


if __name__ == "__main__":
    unittest.main()
