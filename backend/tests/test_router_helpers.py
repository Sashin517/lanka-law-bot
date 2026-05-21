"""Unit tests for the router node's helper functions.

Tests retrieval plan building, entity extraction, template selection,
and verify-request detection — all pure functions that don't need
LLM mocks.
"""

from __future__ import annotations

import unittest

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
from app.agents.nodes.router_node import (
    _build_retrieval_plan,
    _extract_entity_filters,
    _is_document_summary_query,
    _is_verify_request,
)


def _make_plan(**overrides) -> IntentRoutePlan:
    """Build a valid IntentRoutePlan with sensible defaults."""
    data = {
        "raw_query": "test query",
        "normalized_query": "test query",
        "route": IntentRoute.QUICK_QA,
        "task_type": LegalTaskType.QA,
        "target_corpus": TargetCorpus.ACTS,
        "answer_mode": AnswerMode.DIRECT_ANSWER,
        "retrieval_depth": RetrievalDepth.FAST,
        "entities": LegalQueryEntities(),
        "requires_user_document": False,
        "requires_template": False,
        "needs_clarification": False,
        "clarification_question": None,
        "confidence": RouteConfidence.HIGH,
        "routing_reason": "Test.",
    }
    data.update(overrides)
    return IntentRoutePlan(**data)


class TestBuildRetrievalPlan(unittest.TestCase):
    """Test the _build_retrieval_plan helper."""

    def test_no_documents_uses_legal_only(self):
        plan = _make_plan()
        result = _build_retrieval_plan("what is section 12?", plan, [])
        self.assertTrue(result["use_legal_corpus"])
        self.assertFalse(result["use_user_documents"])

    def test_unsupported_skips_legal_corpus(self):
        plan = _make_plan(
            route=IntentRoute.UNSUPPORTED,
            task_type=LegalTaskType.UNSUPPORTED,
            target_corpus=TargetCorpus.NONE,
            answer_mode=AnswerMode.UNSUPPORTED,
            retrieval_depth=RetrievalDepth.NONE,
        )
        result = _build_retrieval_plan("hello world", plan, [])
        self.assertFalse(result["use_legal_corpus"])

    def test_document_summary_uses_user_docs_only(self):
        plan = _make_plan()
        result = _build_retrieval_plan(
            "summarize this document", plan, ["doc-1"],
        )
        self.assertFalse(result["use_legal_corpus"])
        self.assertTrue(result["use_user_documents"])
        self.assertEqual(result["user_doc_top_k"], 8)

    def test_review_uses_both_corpora(self):
        plan = _make_plan(
            route=IntentRoute.REVIEW,
            task_type=LegalTaskType.REVIEW,
            target_corpus=TargetCorpus.USER_DOCUMENT,
            answer_mode=AnswerMode.REVIEW_REPORT,
            requires_user_document=True,
        )
        result = _build_retrieval_plan(
            "review this contract", plan, ["doc-1"],
        )
        self.assertTrue(result["use_legal_corpus"])
        self.assertTrue(result["use_user_documents"])

    def test_research_with_docs_enables_user_documents(self):
        """Deep Research should search user docs when document_ids present."""
        plan = _make_plan(
            route=IntentRoute.DEEP_RESEARCH,
            task_type=LegalTaskType.RESEARCH,
            target_corpus=TargetCorpus.BOTH,
            answer_mode=AnswerMode.RESEARCH_MEMO,
            retrieval_depth=RetrievalDepth.ITERATIVE,
        )
        result = _build_retrieval_plan(
            "compare these clauses with the law", plan, ["doc-1"],
        )
        self.assertTrue(result["use_legal_corpus"])
        self.assertTrue(result["use_user_documents"])

    def test_research_without_docs_skips_user_documents(self):
        plan = _make_plan(
            route=IntentRoute.DEEP_RESEARCH,
            task_type=LegalTaskType.RESEARCH,
            target_corpus=TargetCorpus.BOTH,
            answer_mode=AnswerMode.RESEARCH_MEMO,
            retrieval_depth=RetrievalDepth.ITERATIVE,
        )
        result = _build_retrieval_plan("compare acts", plan, [])
        self.assertTrue(result["use_legal_corpus"])
        self.assertFalse(result["use_user_documents"])


class TestExtractEntityFilters(unittest.TestCase):
    """Test entity filter extraction."""

    def test_quick_qa_extracts_year_and_act(self):
        plan = _make_plan(
            entities=LegalQueryEntities(
                act_names=["Rent Act"],
                dates=["1972"],
            ),
        )
        year, act = _extract_entity_filters(plan)
        self.assertEqual(year, 1972)
        self.assertEqual(act, "Rent Act")

    def test_non_qa_routes_skip_filters(self):
        plan = _make_plan(
            route=IntentRoute.DEEP_RESEARCH,
            task_type=LegalTaskType.RESEARCH,
            target_corpus=TargetCorpus.BOTH,
            answer_mode=AnswerMode.RESEARCH_MEMO,
            retrieval_depth=RetrievalDepth.ITERATIVE,
            entities=LegalQueryEntities(act_names=["Rent Act"]),
        )
        year, act = _extract_entity_filters(plan)
        self.assertIsNone(year)
        self.assertIsNone(act)

    def test_multiple_acts_skip_filter(self):
        """Ambiguous when multiple acts present — don't filter."""
        plan = _make_plan(
            entities=LegalQueryEntities(
                act_names=["Rent Act", "Penal Code"],
            ),
        )
        _, act = _extract_entity_filters(plan)
        self.assertIsNone(act)


class TestDocumentSummaryDetection(unittest.TestCase):

    def test_summary_phrases(self):
        self.assertTrue(_is_document_summary_query("summarize this document"))
        self.assertTrue(_is_document_summary_query("Summarise this"))
        self.assertTrue(_is_document_summary_query("what does this document say"))

    def test_non_summary(self):
        self.assertFalse(_is_document_summary_query("what is section 12?"))


class TestVerifyRequestDetection(unittest.TestCase):

    def test_verify_section(self):
        self.assertTrue(_is_verify_request("verify section 12 of the Rent Act"))

    def test_does_say(self):
        self.assertTrue(_is_verify_request("does the Penal Code say murder is punishable?"))

    def test_confirm_that(self):
        self.assertTrue(_is_verify_request("confirm that section 5 applies"))

    def test_normal_query_not_verify(self):
        self.assertFalse(_is_verify_request("what is the Rent Act?"))


if __name__ == "__main__":
    unittest.main()
