import asyncio
import unittest

from app.services.intent_routing.models import IntentRoute, TargetCorpus
from app.services.intent_routing.router import SemanticIntentRouter


class _Message:
    def __init__(self, content: str) -> None:
        self.content = content


class _MockLLM:
    def __init__(self, content: str) -> None:
        self.content = content

    async def ainvoke(self, prompt: str):
        self.prompt = prompt
        return _Message(self.content)


class IntentRouterPromptContractTests(unittest.TestCase):
    def test_router_parses_valid_json_output(self):
        llm = _MockLLM(
            """
            {
              "raw_query": "What does section 12 say?",
              "normalized_query": "What does section 12 say?",
              "route": "quick_qa",
              "task_type": "qa",
              "target_corpus": "acts",
              "answer_mode": "direct_answer",
              "retrieval_depth": "fast",
              "entities": {
                "act_names": [],
                "section_refs": ["section 12"],
                "case_names": [],
                "court_names": [],
                "legal_domains": [],
                "document_types": [],
                "party_names": [],
                "dates": [],
                "jurisdiction": "Sri Lanka"
              },
              "requires_user_document": false,
              "requires_template": false,
              "needs_clarification": false,
              "clarification_question": null,
              "confidence": "high",
              "routing_reason": "Specific section query."
            }
            """
        )
        router = SemanticIntentRouter(llm=llm)

        result = asyncio.run(router.classify("What does section 12 say?"))

        self.assertEqual(result.source, "llm")
        self.assertEqual(result.plan.route, IntentRoute.QUICK_QA)

    def test_router_falls_back_on_malformed_json(self):
        router = SemanticIntentRouter(llm=_MockLLM("This is not JSON"))

        result = asyncio.run(router.classify("What does section 12 say?"))

        self.assertEqual(result.source, "fallback_rules")
        self.assertTrue(result.parse_error)
        self.assertEqual(result.plan.route, IntentRoute.QUICK_QA)

    def test_router_falls_back_on_missing_required_fields(self):
        router = SemanticIntentRouter(llm=_MockLLM('{"route": "quick_qa"}'))

        result = asyncio.run(router.classify("What does section 12 say?"))

        self.assertEqual(result.source, "fallback_rules")
        self.assertTrue(result.parse_error)

    def test_router_accepts_low_confidence_clarification_output(self):
        router = SemanticIntentRouter(
            llm=_MockLLM(
                """
                {
                  "raw_query": "review this",
                  "normalized_query": "review this",
                  "route": "review",
                  "task_type": "review",
                  "target_corpus": "user_document",
                  "answer_mode": "review_report",
                  "retrieval_depth": "none",
                  "entities": {
                    "act_names": [],
                    "section_refs": [],
                    "case_names": [],
                    "court_names": [],
                    "legal_domains": [],
                    "document_types": [],
                    "party_names": [],
                    "dates": [],
                    "jurisdiction": "Sri Lanka"
                  },
                  "requires_user_document": true,
                  "requires_template": false,
                  "needs_clarification": true,
                  "clarification_question": "Please provide the document text to review.",
                  "confidence": "low",
                  "routing_reason": "Review intent requires user document content."
                }
                """
            )
        )

        result = asyncio.run(router.classify("review this"))

        self.assertEqual(result.source, "llm")
        self.assertTrue(result.plan.needs_clarification)
        self.assertEqual(result.plan.target_corpus, TargetCorpus.USER_DOCUMENT)


if __name__ == "__main__":
    unittest.main()
