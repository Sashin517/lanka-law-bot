"""Unit tests for the router node's helper functions.

Tests retrieval plan building, document-summary detection, and
verify-request detection — pure helpers that do not need LLM mocks.
"""

from __future__ import annotations

import unittest

from app.agents.nodes.quick_qa_node import _is_verify_request
from app.agents.nodes.router_node import (
    ModeConfig,
    _MODE_CONFIG,
    _build_retrieval_plan,
    _is_document_summary_query,
)
from app.agents.state import AgentState


def _state(question: str, mode: str = "quick_qa", document_ids: list[str] | None = None) -> AgentState:
    return AgentState(
        question=question,
        mode=mode,
        document_ids=document_ids or [],
    )


def _config(mode: str) -> ModeConfig:
    return _MODE_CONFIG[mode]


class TestBuildRetrievalPlan(unittest.TestCase):
    """Test the _build_retrieval_plan helper."""

    def test_no_documents_uses_legal_only(self):
        result = _build_retrieval_plan(
            _state("what is section 12?"),
            _config("quick_qa"),
        )
        self.assertTrue(result["use_legal_corpus"])
        self.assertFalse(result["use_user_documents"])

    def test_document_summary_uses_user_docs_only(self):
        result = _build_retrieval_plan(
            _state("summarize this document", document_ids=["doc-1"]),
            _config("quick_qa"),
        )
        self.assertFalse(result["use_legal_corpus"])
        self.assertTrue(result["use_user_documents"])
        self.assertEqual(result["user_doc_top_k"], 8)

    def test_review_with_docs_uses_both_corpora(self):
        result = _build_retrieval_plan(
            _state("review this contract", mode="review", document_ids=["doc-1"]),
            _config("review"),
        )
        self.assertTrue(result["use_legal_corpus"])
        self.assertTrue(result["use_user_documents"])

    def test_research_with_docs_enables_user_documents(self):
        result = _build_retrieval_plan(
            _state(
                "compare these clauses with the law",
                mode="deep_research",
                document_ids=["doc-1"],
            ),
            _config("deep_research"),
        )
        self.assertTrue(result["use_legal_corpus"])
        self.assertTrue(result["use_user_documents"])

    def test_research_without_docs_skips_user_documents(self):
        result = _build_retrieval_plan(
            _state("compare acts", mode="deep_research"),
            _config("deep_research"),
        )
        self.assertTrue(result["use_legal_corpus"])
        self.assertFalse(result["use_user_documents"])

    def test_quick_qa_extracts_year_and_act_filters(self):
        result = _build_retrieval_plan(
            _state("What does the Rent Act of 1972 say about eviction?"),
            _config("quick_qa"),
        )
        self.assertEqual(result["year_filters"], [1972])
        self.assertEqual(result["act_name_filters"], ["Rent Act"])


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
        self.assertTrue(
            _is_verify_request("does the Penal Code say murder is punishable?")
        )

    def test_confirm_that(self):
        self.assertTrue(_is_verify_request("confirm that section 5 applies"))

    def test_normal_query_not_verify(self):
        self.assertFalse(_is_verify_request("what is the Rent Act?"))


if __name__ == "__main__":
    unittest.main()
