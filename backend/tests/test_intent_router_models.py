import unittest

from pydantic import ValidationError

from app.services.intent_routing.models import (
    AnswerMode,
    IntentRoute,
    IntentRoutePlan,
    LegalQueryEntities,
    LegalTaskType,
    RetrievalDepth,
    RouteConfidence,
    TargetCorpus,
)


def _valid_plan(**overrides):
    data = {
        "raw_query": "What does section 12 say?",
        "normalized_query": "What does section 12 say?",
        "route": IntentRoute.QUICK_QA,
        "task_type": LegalTaskType.QA,
        "target_corpus": TargetCorpus.ACTS,
        "answer_mode": AnswerMode.DIRECT_ANSWER,
        "retrieval_depth": RetrievalDepth.FAST,
        "entities": LegalQueryEntities(section_refs=["section 12"]),
        "requires_user_document": False,
        "requires_template": False,
        "needs_clarification": False,
        "clarification_question": None,
        "confidence": RouteConfidence.HIGH,
        "routing_reason": "Specific section query.",
    }
    data.update(overrides)
    return IntentRoutePlan(**data)


class IntentRouterModelTests(unittest.TestCase):
    def test_enum_values_match_route_contract(self):
        self.assertEqual(IntentRoute.QUICK_QA.value, "quick_qa")
        self.assertEqual(IntentRoute.DEEP_RESEARCH.value, "deep_research")
        self.assertEqual(IntentRoute.DRAFTING.value, "drafting")
        self.assertEqual(IntentRoute.REVIEW.value, "review")
        self.assertEqual(IntentRoute.REASONING.value, "reasoning")
        self.assertEqual(IntentRoute.UNSUPPORTED.value, "unsupported")

    def test_valid_route_plan_parses(self):
        plan = _valid_plan()

        self.assertEqual(plan.route, IntentRoute.QUICK_QA)
        self.assertEqual(plan.entities.section_refs, ["section 12"])

    def test_invalid_enum_value_fails_validation(self):
        with self.assertRaises(ValidationError):
            _valid_plan(route="research_agent")

    def test_clarification_requires_question(self):
        with self.assertRaises(ValidationError):
            _valid_plan(needs_clarification=True, clarification_question=None)

    def test_unsupported_requires_no_corpus_or_retrieval(self):
        with self.assertRaises(ValidationError):
            _valid_plan(
                route=IntentRoute.UNSUPPORTED,
                task_type=LegalTaskType.UNSUPPORTED,
                answer_mode=AnswerMode.UNSUPPORTED,
                target_corpus=TargetCorpus.BOTH,
                retrieval_depth=RetrievalDepth.NONE,
            )

    def test_review_requires_user_document_flag(self):
        with self.assertRaises(ValidationError):
            _valid_plan(
                route=IntentRoute.REVIEW,
                task_type=LegalTaskType.REVIEW,
                target_corpus=TargetCorpus.USER_DOCUMENT,
                answer_mode=AnswerMode.REVIEW_REPORT,
                retrieval_depth=RetrievalDepth.NONE,
                requires_user_document=False,
            )


if __name__ == "__main__":
    unittest.main()
