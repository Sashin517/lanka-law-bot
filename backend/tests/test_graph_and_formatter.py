"""Unit tests for the graph builder and formatter node.

Tests graph compilation, node registration, edge wiring, and
the formatter's response structure.
"""

from __future__ import annotations

import unittest

from app.agents.state import (
    AgentState,
    CitedClaim,
    GroundingResult,
    SourceChunk,
)
from app.agents.nodes.formatter_node import formatter_node
from app.agents.nodes.unsupported_node import unsupported_node


class TestGraphCompilation(unittest.TestCase):
    """Verify the graph compiles without errors."""

    def test_graph_compiles(self):
        """Graph should compile with all 10 nodes registered."""
        # Import inside test to catch import-time errors
        from app.agents.graph import build_graph

        graph = build_graph()
        self.assertIsNotNone(graph)


class TestFormatterNode(unittest.TestCase):
    """Verify the formatter produces frontend-compatible output."""

    def _make_state(self, **overrides) -> AgentState:
        defaults = {
            "question": "What is Section 12?",
            "route": "quick_qa",
            "task_type": "qa",
            "answer_mode": "direct_answer",
            "target_corpus": "acts",
            "route_confidence": "high",
            "summary": "Section 12 prohibits eviction.",
            "analysis": [
                CitedClaim(
                    statement="Section 12 of the Rent Act prohibits eviction.",
                    citation_ids=["[LAW-1]"],
                ),
            ],
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

    async def _run_formatter(self, state: AgentState) -> dict:
        result = await formatter_node(state)
        return result

    def test_final_response_structure(self):
        """Formatter should produce all required response keys."""
        import asyncio
        state = self._make_state()
        result = asyncio.run(self._run_formatter(state))

        self.assertIn("final_response", result)
        resp = result["final_response"]

        # All expected keys
        self.assertIn("route", resp)
        self.assertIn("answer", resp)
        self.assertIn("results", resp)
        self.assertIn("analysis", resp)
        self.assertIn("sources", resp)
        self.assertIn("confidence", resp)
        self.assertIn("grounding_score", resp)
        self.assertIn("disclaimer", resp)

    def test_results_array_format(self):
        """Each result should have id, title, subtitle, excerpt, score."""
        import asyncio
        state = self._make_state()
        result = asyncio.run(self._run_formatter(state))
        resp = result["final_response"]

        self.assertEqual(len(resp["results"]), 1)
        item = resp["results"][0]
        self.assertEqual(item["id"], "[LAW-1]")
        self.assertIn("Rent Act", item["title"])
        self.assertIn("1972", item["subtitle"])

    def test_analysis_format(self):
        """Analysis items should have statement and citations."""
        import asyncio
        state = self._make_state()
        result = asyncio.run(self._run_formatter(state))
        resp = result["final_response"]

        self.assertEqual(len(resp["analysis"]), 1)
        claim = resp["analysis"][0]
        self.assertIn("statement", claim)
        self.assertIn("citations", claim)
        self.assertEqual(claim["citations"], ["[LAW-1]"])

    def test_grounding_score_in_response(self):
        import asyncio
        state = self._make_state()
        result = asyncio.run(self._run_formatter(state))
        resp = result["final_response"]

        self.assertAlmostEqual(resp["grounding_score"], 0.95)

    def test_empty_state_produces_valid_response(self):
        """Formatter should handle empty analysis gracefully."""
        import asyncio
        state = self._make_state(
            summary="No results found.",
            analysis=[],
            retrieved_sources=[],
            confidence="low",
        )
        result = asyncio.run(self._run_formatter(state))
        resp = result["final_response"]

        self.assertEqual(resp["answer"], "No results found.")
        self.assertEqual(resp["results"], [])
        self.assertEqual(resp["analysis"], [])


class TestUnsupportedNode(unittest.TestCase):
    """Verify the unsupported node returns expected structure."""

    def test_unsupported_response(self):
        import asyncio
        state = AgentState(question="What's the weather?")
        result = asyncio.run(unsupported_node(state))

        self.assertIn("outside the supported", result["summary"])
        self.assertEqual(result["analysis"], [])
        self.assertEqual(result["confidence"], "low")


if __name__ == "__main__":
    unittest.main()
