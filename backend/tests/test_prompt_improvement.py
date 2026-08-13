from __future__ import annotations

import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROMPT_FILE = (
    BACKEND_DIR / "app" / "services" / "generation" / "prompt_improvement_prompt.py"
)
SERVICE_FILE = (
    BACKEND_DIR / "app" / "services" / "generation" / "prompt_improvement_service.py"
)


class TestPromptImprovementContract(unittest.TestCase):
    def test_prompt_requires_intent_and_fact_preservation(self):
        prompt = PROMPT_FILE.read_text(encoding="utf-8").lower()

        self.assertIn("preserving intent", prompt)
        self.assertIn("preserve user intent and key facts", prompt)
        self.assertIn("do not invent facts, legal outcomes, sections, or case details", prompt)
        self.assertIn("[fact_needed]", prompt)

    def test_quick_qa_guidance_stays_focused_without_inventing_details(self):
        guidance = PROMPT_FILE.read_text(encoding="utf-8").lower()

        self.assertIn("produce one focused legal question", guidance)
        self.assertIn("remove fluff and keep concise", guidance)

    def test_service_has_overcompression_guard_and_fallback(self):
        service = SERVICE_FILE.read_text(encoding="utf-8")

        self.assertIn("def _looks_overcompressed", service)
        self.assertIn("def _fact_preserving_fallback", service)
        self.assertIn("_looks_overcompressed(draft, improved_prompt)", service)
        self.assertIn("not add remedies or issues", service)


if __name__ == "__main__":
    unittest.main()
