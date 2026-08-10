from __future__ import annotations

import unittest

from app.agents.prompts.draft_revision_context import prepend_revision_context


class TestDraftRevisionContext(unittest.TestCase):
    def test_existing_draft_and_instruction_precede_research_context(self):
        context = prepend_revision_context(
            "## Prior Research\nAuthority findings",
            "# Existing Contract\nOriginal terms",
            "Align the privacy clauses with the new Act.",
        )

        self.assertLess(context.index("# Existing Contract"), context.index("## Prior Research"))
        self.assertIn("## Revision Instruction", context)
        self.assertIn("Align the privacy clauses", context)


if __name__ == "__main__":
    unittest.main()
