import unittest

from app.services.intent_routing.fallback import build_fallback_route_plan
from app.services.intent_routing.models import IntentRoute, RouteConfidence


class IntentRouterFallbackTests(unittest.TestCase):
    def test_fallback_routes_drafting(self):
        plan = build_fallback_route_plan("Draft a tenancy agreement", "test")
        self.assertEqual(plan.route, IntentRoute.DRAFTING)

    def test_fallback_routes_review(self):
        plan = build_fallback_route_plan("Review this contract for risk", "test")
        self.assertEqual(plan.route, IntentRoute.REVIEW)
        self.assertTrue(plan.requires_user_document)

    def test_fallback_routes_deep_research(self):
        plan = build_fallback_route_plan(
            "Find leading cases on natural justice",
            "test",
        )
        self.assertEqual(plan.route, IntentRoute.DEEP_RESEARCH)

    def test_fallback_routes_reasoning(self):
        plan = build_fallback_route_plan("Is this dismissal lawful?", "test")
        self.assertEqual(plan.route, IntentRoute.REASONING)

    def test_fallback_routes_quick_qa(self):
        plan = build_fallback_route_plan("What does section 12 say?", "test")
        self.assertEqual(plan.route, IntentRoute.QUICK_QA)

    def test_fallback_defaults_vague_query_to_low_confidence_quick_qa(self):
        plan = build_fallback_route_plan("help", "test")
        self.assertEqual(plan.route, IntentRoute.QUICK_QA)
        self.assertEqual(plan.confidence, RouteConfidence.LOW)


if __name__ == "__main__":
    unittest.main()
