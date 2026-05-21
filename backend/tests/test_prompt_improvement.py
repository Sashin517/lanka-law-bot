from __future__ import annotations

import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROMPT_FILE = BACKEND_DIR / "app" / "services" / "generation" / "prompt_improvement_prompt.py"
SERVICE_FILE = BACKEND_DIR / "app" / "services" / "generation" / "prompt_improvement_service.py"


class TestPromptImprovementContract(unittest.TestCase):
    def test_prompt_requires_fact_pattern_preservation(self):
        prompt = PROMPT_FILE.read_text(encoding="utf-8").lower()

        self.assertIn("retain legally material facts", prompt)
        self.assertIn("requested remedy", prompt)
        self.assertIn("do not introduce a new remedy", prompt)
        self.assertIn("without materially shortening it", prompt)

    def test_quick_qa_guidance_does_not_encourage_fact_loss(self):
        guidance = PROMPT_FILE.read_text(encoding="utf-8").lower()

        self.assertIn("compress away material facts", guidance)

    def test_service_has_overcompression_guard_and_fallback(self):
        service = SERVICE_FILE.read_text(encoding="utf-8")

        self.assertIn("def _looks_overcompressed", service)
        self.assertIn("def _fact_preserving_fallback", service)
        self.assertIn("_looks_overcompressed(draft, improved_prompt)", service)
        self.assertIn("not add remedies or issues", service)


if __name__ == "__main__":
    unittest.main()
