"""Unit tests for the verify node's citation target extraction.

Pure function tests — no LLM or retrieval mocks needed.
"""

from __future__ import annotations

import unittest

from app.agents.nodes.verify_node import _extract_citation_target


class TestExtractCitationTarget(unittest.TestCase):
    """Test regex-based extraction of act name and section reference."""

    def test_section_of_act(self):
        """'Section X of the [Act]' pattern."""
        act, section = _extract_citation_target(
            "Does Section 12 of the Rent Act say tenants can be evicted?"
        )
        self.assertEqual(act, "Rent Act")
        self.assertEqual(section, "Section 12")

    def test_section_of_act_without_the(self):
        act, section = _extract_citation_target(
            "Verify Section 300 of Penal Code states murder is punishable"
        )
        self.assertEqual(act, "Penal Code")
        self.assertEqual(section, "Section 300")

    def test_act_section_reversed_order(self):
        """'[Act] Section X' pattern."""
        act, section = _extract_citation_target(
            "The Penal Code Section 294 mentions obscenity"
        )
        self.assertIn("Penal Code", act or "")
        self.assertIn("Section 294", section or "")

    def test_act_name_only_no_section(self):
        act, section = _extract_citation_target(
            "What does the Rent Act say about eviction?"
        )
        self.assertIsNotNone(act)
        self.assertIn("Rent Act", act)
        self.assertIsNone(section)

    def test_no_legal_reference(self):
        act, section = _extract_citation_target("Hello world")
        self.assertIsNone(act)
        self.assertIsNone(section)

    def test_section_with_subsection_letter(self):
        act, section = _extract_citation_target(
            "Section 12A of the Companies Act provides"
        )
        self.assertEqual(act, "Companies Act")
        self.assertEqual(section, "Section 12A")

    def test_ordinance_reference(self):
        act, _ = _extract_citation_target(
            "Under the Motor Traffic Ordinance No. 14"
        )
        self.assertIsNotNone(act)
        self.assertIn("Motor Traffic Ordinance", act)


if __name__ == "__main__":
    unittest.main()
