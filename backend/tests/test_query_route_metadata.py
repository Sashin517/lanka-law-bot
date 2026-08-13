import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from app.api.endpoints import query_routes
from app.schemas.requests import LegalQuery, QueryMode


class QueryRouteMetadataTests(unittest.TestCase):
    def test_search_endpoint_returns_formatter_response(self):
        final_response = {
            "route": {
                "route": "quick_qa",
                "task_type": "qa",
                "answer_mode": "direct_answer",
                "target_corpus": "both",
                "confidence": "high",
                "needs_clarification": False,
                "clarification_question": None,
            },
            "answer": "answer",
            "markdown_content": "**answer**",
            "sources": [],
            "confidence": "high",
            "grounding_score": 0.9,
            "disclaimer": "Research information only.",
            "execution_trace": {
                "plan_type": "fast_path",
                "steps_executed": [],
                "total_steps": 0,
                "planning_reasoning": "",
                "completed_agents": ["quick_qa"],
            },
        }
        graph = AsyncMock()
        graph.ainvoke = AsyncMock(return_value={"final_response": final_response})

        with patch.object(query_routes, "get_graph", return_value=graph):
            response = asyncio.run(
                query_routes.search_law(
                    LegalQuery(question="test", mode=QueryMode.QUICK_QA)
                )
            )

        self.assertEqual(response["answer"], "answer")
        self.assertEqual(response["route"]["route"], "quick_qa")
        self.assertIn("sources", response)
        self.assertIn("markdown_content", response)
        self.assertNotIn("analysis", response)
        graph.ainvoke.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
