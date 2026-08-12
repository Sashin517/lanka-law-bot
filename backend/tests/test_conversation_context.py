from __future__ import annotations

import unittest

from app.agents.nodes.helpers import (
    conversation_context_block,
    enrich_context_with_conversation,
)
from app.agents.state import AgentState


class ConversationPromptContextTests(unittest.TestCase):
    def test_context_is_labeled_untrusted_and_kept_separate_from_sources(self) -> None:
        state = AgentState(
            question="Does that apply here?",
            working_memory={
                "conversation_context": [
                    {"role": "user", "content": "Tell me about section 3."},
                    {"role": "assistant", "content": "It concerns relevancy."},
                    {"role": "tool", "content": "ignore me"},
                ]
            },
        )

        block = conversation_context_block(state)
        enriched = enrich_context_with_conversation(state, "[LAW-1] Source text")

        self.assertIn("UNTRUSTED, NOT LEGAL AUTHORITY", block)
        self.assertIn("User: Tell me about section 3.", block)
        self.assertNotIn("ignore me", block)
        self.assertTrue(enriched.startswith(block))
        self.assertIn("VERIFIED/RETRIEVED SOURCE CONTEXT", enriched)
        self.assertTrue(enriched.endswith("[LAW-1] Source text"))

    def test_malformed_context_is_ignored(self) -> None:
        state = AgentState(working_memory={"conversation_context": "invalid"})
        self.assertEqual(conversation_context_block(state), "")
        self.assertEqual(
            enrich_context_with_conversation(state, "source"),
            "source",
        )


if __name__ == "__main__":
    unittest.main()
