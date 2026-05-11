"""Unit tests for the drafting template selection logic.

Pure function tests — no LLM or retrieval mocks needed.
"""

from __future__ import annotations

import unittest

from app.agents.nodes.drafting_node import _select_template
from app.agents.templates import TEMPLATE_REGISTRY


class TestTemplateRegistry(unittest.TestCase):
    """Verify all expected templates are registered."""

    def test_all_templates_present(self):
        expected = {"contract", "pleading", "notice", "affidavit"}
        self.assertEqual(set(TEMPLATE_REGISTRY.keys()), expected)

    def test_templates_not_empty(self):
        for key, template in TEMPLATE_REGISTRY.items():
            self.assertGreater(len(template), 100, f"{key} template is too short")


class TestSelectTemplate(unittest.TestCase):
    """Verify template selection logic."""

    def test_explicit_answer_mode_match(self):
        """answer_mode takes priority over keyword detection."""
        result = _select_template("some question", "affidavit")
        self.assertEqual(result, "affidavit")

    def test_keyword_contract(self):
        result = _select_template("Draft a lease agreement for office space", "")
        self.assertEqual(result, "contract")

    def test_keyword_pleading(self):
        result = _select_template("Prepare a plaint for breach of contract", "")
        self.assertEqual(result, "pleading")

    def test_keyword_notice(self):
        result = _select_template("Write a letter of demand for unpaid rent", "")
        self.assertEqual(result, "notice")

    def test_keyword_affidavit(self):
        result = _select_template("Draft an affidavit for court proceedings", "")
        self.assertEqual(result, "affidavit")

    def test_default_fallback(self):
        """No keywords or answer_mode match → default to contract."""
        result = _select_template("draft something legal", "")
        self.assertEqual(result, "contract")

    def test_keyword_case_insensitive(self):
        result = _select_template("Draft a PETITION to the Supreme Court", "")
        self.assertEqual(result, "pleading")


if __name__ == "__main__":
    unittest.main()
