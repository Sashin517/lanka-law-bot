"""Unit tests for the grounding prompt template.

Validates that the prompt template has all required placeholders
and structural elements needed by the grounding verifier node.
"""

from __future__ import annotations

import unittest

from app.agents.prompts.grounding_prompt import GROUNDING_JUDGE_PROMPT
from app.agents.prompts.deep_research_prompt import DEEP_RESEARCH_PROMPT
from app.agents.prompts.reasoning_prompt import REASONING_PROMPT
from app.agents.prompts.drafting_prompt import DRAFTING_PROMPT
from app.agents.prompts.review_prompt import REVIEW_PROMPT
from app.agents.prompts.verify_prompt import VERIFY_PROMPT
from app.agents.prompts.decomposition_prompt import DECOMPOSITION_PROMPT


class TestGroundingPrompt(unittest.TestCase):
    """Validate the grounding judge prompt structure."""

    def test_has_required_placeholders(self):
        self.assertIn("{summary}", GROUNDING_JUDGE_PROMPT)
        self.assertIn("{claims}", GROUNDING_JUDGE_PROMPT)
        self.assertIn("{sources}", GROUNDING_JUDGE_PROMPT)

    def test_instructs_json_output(self):
        self.assertIn("valid JSON only", GROUNDING_JUDGE_PROMPT)
        self.assertIn("is_grounded", GROUNDING_JUDGE_PROMPT)
        self.assertIn("grounding_score", GROUNDING_JUDGE_PROMPT)

    def test_no_fabrication_instruction(self):
        """Prompt must explicitly forbid fabrication."""
        lower = GROUNDING_JUDGE_PROMPT.lower()
        self.assertTrue(
            "not grounded" in lower or "not appear" in lower
        )


class TestWorkerPrompts(unittest.TestCase):
    """Validate all worker prompts have required structure."""

    def test_deep_research_placeholders(self):
        self.assertIn("{question}", DEEP_RESEARCH_PROMPT)
        self.assertIn("{context}", DEEP_RESEARCH_PROMPT)
        self.assertIn("{sub_queries}", DEEP_RESEARCH_PROMPT)

    def test_reasoning_placeholders(self):
        self.assertIn("{question}", REASONING_PROMPT)
        self.assertIn("{context}", REASONING_PROMPT)

    def test_reasoning_has_irac(self):
        self.assertIn("IRAC", REASONING_PROMPT)
        self.assertIn("Issue", REASONING_PROMPT)
        self.assertIn("Rule", REASONING_PROMPT)
        self.assertIn("Application", REASONING_PROMPT)
        self.assertIn("Conclusion", REASONING_PROMPT)

    def test_drafting_placeholders(self):
        self.assertIn("{question}", DRAFTING_PROMPT)
        self.assertIn("{context}", DRAFTING_PROMPT)
        self.assertIn("{template}", DRAFTING_PROMPT)

    def test_review_placeholders(self):
        self.assertIn("{question}", REVIEW_PROMPT)
        self.assertIn("{context}", REVIEW_PROMPT)

    def test_review_dual_citation_instruction(self):
        self.assertIn("[DOC-*]", REVIEW_PROMPT)
        self.assertIn("[LAW-*]", REVIEW_PROMPT)

    def test_verify_placeholders(self):
        self.assertIn("{question}", VERIFY_PROMPT)
        self.assertIn("{context}", VERIFY_PROMPT)

    def test_verify_has_verdict_types(self):
        self.assertIn("CONFIRMED", VERIFY_PROMPT)
        self.assertIn("PARTIALLY CORRECT", VERIFY_PROMPT)
        self.assertIn("UNCONFIRMED", VERIFY_PROMPT)

    def test_decomposition_placeholders(self):
        self.assertIn("{question}", DECOMPOSITION_PROMPT)

    def test_all_prompts_forbid_fabrication(self):
        """Every worker prompt must include an anti-hallucination rule."""
        prompts = [
            DEEP_RESEARCH_PROMPT, REASONING_PROMPT,
            DRAFTING_PROMPT, REVIEW_PROMPT, VERIFY_PROMPT,
        ]
        for prompt in prompts:
            self.assertIn(
                "NEVER",
                prompt,
                f"Prompt missing anti-hallucination instruction",
            )

    def test_all_prompts_require_json(self):
        prompts = [
            DEEP_RESEARCH_PROMPT, REASONING_PROMPT,
            DRAFTING_PROMPT, REVIEW_PROMPT, VERIFY_PROMPT,
            DECOMPOSITION_PROMPT,
        ]
        for prompt in prompts:
            self.assertIn(
                "valid JSON only",
                prompt,
                f"Prompt missing JSON output instruction",
            )


if __name__ == "__main__":
    unittest.main()
