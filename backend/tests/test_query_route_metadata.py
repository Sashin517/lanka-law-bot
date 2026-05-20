import asyncio
import importlib
import sys
import types
import unittest
from unittest.mock import patch

from app.schemas.responses import ConfidenceLevel, LegalResponse, RouteMetadata


def _route_metadata(route: str = "quick_qa") -> RouteMetadata:
    return RouteMetadata(
        route=route,
        task_type="qa",
        answer_mode="direct_answer",
        target_corpus="acts",
        confidence="high",
        needs_clarification=False,
        clarification_question=None,
        routing_reason="test route",
    )


class QueryRouteMetadataTests(unittest.TestCase):
    def test_search_endpoint_returns_route_metadata(self):
        fake_agent = types.ModuleType("app.agent")

        async def fake_process_query_with_route(question: str):
            route = _route_metadata()
            return (
                LegalResponse(
                    summary="answer",
                    analysis=[],
                    sources=[],
                    confidence=ConfidenceLevel.HIGH,
                    route=route,
                ),
                route,
            )

        fake_agent.process_query_with_route = fake_process_query_with_route

        with patch.dict(sys.modules, {"app.agent": fake_agent}):
            module_name = "app.api.endpoints.query_routes"
            sys.modules.pop(module_name, None)
            query_routes = importlib.import_module(module_name)

            response = asyncio.run(
                query_routes.search_law(query_routes.LegalQuery(question="test"))
            )

        self.assertEqual(response["answer"], "answer")
        self.assertEqual(response["route"]["route"], "quick_qa")
        self.assertIn("analysis", response)
        self.assertIn("sources", response)


if __name__ == "__main__":
    unittest.main()
