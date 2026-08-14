"""Unit tests for lean legal-document parsing options."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.config import settings
from app.services.ingestion.document_parser import DocumentParser


class TestLeanDoclingPipeline(unittest.TestCase):
    def test_pdf_pipeline_disables_heavy_enrichment(self):
        options = DocumentParser._build_pdf_pipeline_options()
        self.assertFalse(options.do_table_structure)
        self.assertFalse(options.do_code_enrichment)
        self.assertFalse(options.do_formula_enrichment)
        self.assertFalse(options.do_picture_classification)
        self.assertFalse(options.do_picture_description)
        self.assertFalse(options.do_chart_extraction)
        self.assertFalse(options.generate_page_images)
        self.assertFalse(options.generate_picture_images)
        self.assertEqual(options.ocr_batch_size, 1)
        self.assertEqual(options.layout_batch_size, 1)
        self.assertEqual(options.table_batch_size, 1)
        self.assertEqual(
            options.accelerator_options.num_threads, settings.DOCLING_NUM_THREADS
        )
        self.assertEqual(options.accelerator_options.device, settings.DOCLING_DEVICE)

    def test_native_text_threshold(self):
        short = "x" * (settings.DOCLING_NATIVE_TEXT_MIN_CHARS - 1)
        long = "x" * settings.DOCLING_NATIVE_TEXT_MIN_CHARS
        self.assertFalse(DocumentParser._has_usable_native_text(short))
        self.assertTrue(DocumentParser._has_usable_native_text(long))

    def test_text_pdf_skips_docling_when_native_text_is_usable(self):
        parser = DocumentParser()
        source = Path("contract.pdf")
        with (
            patch.object(
                DocumentParser,
                "_extract_native_pdf_text",
                return_value="Native legal text " * 20,
            ) as native,
            patch(
                "docling.document_converter.DocumentConverter",
                side_effect=AssertionError("Docling should not run for text PDFs"),
            ),
        ):
            markdown = parser._convert_with_docling(source)

        self.assertIn("Native legal text", markdown)
        native.assert_called_once_with(source)


if __name__ == "__main__":
    unittest.main()
