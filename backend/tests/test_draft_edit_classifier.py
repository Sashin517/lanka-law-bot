from __future__ import annotations

import unittest

from app.services.generation.edit_classifier import classify_edit_complexity


class TestDraftEditClassifier(unittest.TestCase):
    def test_small_local_selection_uses_light_path(self):
        self.assertEqual(
            classify_edit_complexity("Make this more formal", "short text", "draft"),
            "light",
        )

    def test_heavy_signal_overrides_small_selection(self):
        self.assertEqual(
            classify_edit_complexity(
                "Rewrite this based on recent amendments",
                "short text",
                "draft",
            ),
            "heavy",
        )

    def test_document_wide_instruction_without_selection_is_heavy(self):
        self.assertEqual(
            classify_edit_complexity("Update the whole document", None, "draft"),
            "heavy",
        )

    def test_long_selection_is_heavy(self):
        self.assertEqual(
            classify_edit_complexity("Improve this", "x" * 2_001, "draft"),
            "heavy",
        )

    def test_heavy_matching_is_case_insensitive(self):
        self.assertEqual(
            classify_edit_complexity("Use SUPREME COURT authorities", "text", "draft"),
            "heavy",
        )

    def test_local_insertion_defaults_to_light(self):
        self.assertEqual(
            classify_edit_complexity("Add a penalty clause here", None, "draft"),
            "light",
        )


if __name__ == "__main__":
    unittest.main()
