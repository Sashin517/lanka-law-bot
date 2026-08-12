"""Regression tests for deterministic legal-instrument extraction."""

from __future__ import annotations

import unittest

from app.agents.nodes.router_node import _extract_entities_from_query


class TestRouterEntityExtraction(unittest.TestCase):
    def assert_entities(
        self,
        question: str,
        *,
        years: list[int] | None,
        instruments: list[str] | None,
    ) -> None:
        actual_years, actual_instruments = _extract_entities_from_query(question)
        self.assertEqual(actual_years, years)
        self.assertEqual(actual_instruments, instruments)

    def test_companies_act_and_year(self) -> None:
        self.assert_entities(
            "What restrictions must the articles of a private company contain "
            "under Section 27 of the Companies Act, No. 7 of 2007?",
            years=[2007],
            instruments=["Companies Act"],
        )

    def test_question_auxiliary_is_not_part_of_act_name(self) -> None:
        self.assert_entities(
            "Can the Electronic Transactions Act be relied upon to satisfy "
            "the legal formalities for a power of attorney?",
            years=None,
            instruments=["Electronic Transactions Act"],
        )

    def test_ordinance_name_is_extracted(self) -> None:
        self.assert_entities(
            "How does Section 3 of the Maternity Benefits Ordinance determine "
            "whether a woman worker is entitled to maternity benefit?",
            years=None,
            instruments=["Maternity Benefits Ordinance"],
        )

    def test_section_suffix_is_not_part_of_act_name(self) -> None:
        self.assert_entities(
            "What time limits apply under Sections 31B and 31C of the "
            "Industrial Disputes Act?",
            years=None,
            instruments=["Industrial Disputes Act"],
        )

    def test_law_suffix_is_supported(self) -> None:
        self.assert_entities(
            "What is the effect under Section 66 of the Partition Law of a "
            "voluntary sale after a lis pendens is registered?",
            years=None,
            instruments=["Partition Law"],
        )

    def test_multiple_instruments_preserve_query_order(self) -> None:
        self.assert_entities(
            "Compare the Companies Act with the Electronic Transactions Act.",
            years=None,
            instruments=["Companies Act", "Electronic Transactions Act"],
        )

    def test_duplicate_years_and_instruments_are_removed(self) -> None:
        self.assert_entities(
            "Does the Companies Act of 2007 differ from the Companies Act, "
            "No. 7 of 2007?",
            years=[2007],
            instruments=["Companies Act"],
        )

    def test_generic_act_reference_is_not_treated_as_a_title(self) -> None:
        self.assert_entities(
            "What Act governs this transaction, and does the Act apply?",
            years=None,
            instruments=None,
        )


if __name__ == "__main__":
    unittest.main()
