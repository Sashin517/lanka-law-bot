from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)

# Docling PDF pipelines load large layout/OCR models into process memory.
# Serialize conversions so concurrent uploads cannot OOM the host.
_DOCLING_CONVERT_LOCK = threading.Lock()


@dataclass(frozen=True)
class ParsedDocument:
    markdown: str
    markdown_path: str
    pages: list[int] = field(default_factory=list)
    tables: list[str] = field(default_factory=list)
    headings: list[str] = field(default_factory=list)
    detected_type: str = "unknown"


class DocumentParser:
    def parse_to_markdown(
        self,
        stored_path: str,
        markdown_path: str,
        document_type_hint: str | None = None,
    ) -> ParsedDocument:
        source = Path(stored_path)
        markdown = self._convert_with_docling(source)
        Path(markdown_path).write_text(markdown, encoding="utf-8")

        return ParsedDocument(
            markdown=markdown,
            markdown_path=markdown_path,
            pages=self._extract_pages(markdown),
            tables=self._extract_tables(markdown),
            headings=self._extract_headings(markdown),
            detected_type=document_type_hint or self._detect_document_type(markdown),
        )

    def _convert_with_docling(self, source: Path) -> str:
        if source.suffix.lower() in {".txt", ".md"}:
            return source.read_text(encoding="utf-8", errors="ignore")

        if source.suffix.lower() == ".pdf" and settings.DOCLING_PREFER_NATIVE_PDF_TEXT:
            native = self._extract_native_pdf_text(source)
            if self._has_usable_native_text(native):
                logger.info(
                    "Using native PDF text for %s (%d chars); skipping Docling models.",
                    source.name,
                    len(native.strip()),
                )
                return native

        try:
            from docling.document_converter import DocumentConverter, PdfFormatOption
            from docling.datamodel.base_models import InputFormat
        except ImportError as exc:
            raise RuntimeError(
                "Docling is not installed. Install backend requirements before ingesting PDFs/DOCX."
            ) from exc

        pipeline_options = self._build_pdf_pipeline_options()
        converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
            }
        )

        with _DOCLING_CONVERT_LOCK:
            logger.info(
                "Docling converting %s (ocr=%s, tables=%s, device=%s).",
                source.name,
                settings.DOCLING_ENABLE_OCR,
                settings.DOCLING_ENABLE_TABLE_STRUCTURE,
                settings.DOCLING_DEVICE,
            )
            result = converter.convert(str(source))
        document = result.document

        if hasattr(document, "export_to_markdown"):
            return document.export_to_markdown()
        if hasattr(document, "export_to_text"):
            return document.export_to_text()
        raise RuntimeError(
            "Docling conversion did not expose a Markdown/text exporter."
        )

    @staticmethod
    def _build_pdf_pipeline_options():
        """Build a lean Docling PDF pipeline for legal text extraction.

        Legal chunking needs readable text and headings. Vision extras
        (tables, charts, picture captions, formula/code models) are disabled
        by default because they dominate RAM and caused ``std::bad_alloc`` /
        Windows paging-file failures under parallel uploads.
        """
        from docling.datamodel.pipeline_options import (
            AcceleratorOptions,
            PdfPipelineOptions,
        )

        return PdfPipelineOptions(
            do_ocr=settings.DOCLING_ENABLE_OCR,
            do_table_structure=settings.DOCLING_ENABLE_TABLE_STRUCTURE,
            do_code_enrichment=False,
            do_formula_enrichment=False,
            do_picture_classification=False,
            do_picture_description=False,
            do_chart_extraction=False,
            generate_page_images=False,
            generate_picture_images=False,
            generate_parsed_pages=False,
            images_scale=1.0,
            ocr_batch_size=1,
            layout_batch_size=1,
            table_batch_size=1,
            accelerator_options=AcceleratorOptions(
                num_threads=max(1, settings.DOCLING_NUM_THREADS),
                device=settings.DOCLING_DEVICE,
            ),
        )

    @staticmethod
    def _extract_native_pdf_text(source: Path) -> str:
        """Extract embedded PDF text without loading Docling ML models."""
        try:
            from pypdf import PdfReader
        except ImportError:
            logger.debug("pypdf is unavailable; falling back to Docling for %s", source.name)
            return ""

        try:
            reader = PdfReader(str(source))
            pages: list[str] = []
            for index, page in enumerate(reader.pages, start=1):
                text = (page.extract_text() or "").strip()
                if text:
                    pages.append(f"## Page {index}\n\n{text}")
            return "\n\n".join(pages).strip()
        except Exception:
            logger.exception("Native PDF text extraction failed for %s", source.name)
            return ""

    @staticmethod
    def _has_usable_native_text(text: str) -> bool:
        return len(text.strip()) >= settings.DOCLING_NATIVE_TEXT_MIN_CHARS

    @staticmethod
    def _extract_pages(markdown: str) -> list[int]:
        pages = set()
        for match in re.finditer(r"\bpage\s+(\d+)\b", markdown, flags=re.IGNORECASE):
            pages.add(int(match.group(1)))
        return sorted(pages)

    @staticmethod
    def _extract_tables(markdown: str) -> list[str]:
        tables: list[str] = []
        current: list[str] = []
        for line in markdown.splitlines():
            if "|" in line and line.count("|") >= 2:
                current.append(line)
            elif current:
                tables.append("\n".join(current))
                current = []
        if current:
            tables.append("\n".join(current))
        return tables

    @staticmethod
    def _extract_headings(markdown: str) -> list[str]:
        return [
            line.lstrip("#").strip()
            for line in markdown.splitlines()
            if line.lstrip().startswith("#")
        ]

    @staticmethod
    def _detect_document_type(markdown: str) -> str:
        text = markdown[:5000].lower()
        signals = {
            "contract": ["agreement", "party", "termination", "confidentiality"],
            "pleading": ["plaintiff", "defendant", "prayer", "petition"],
            "affidavit": ["affidavit", "deponent", "sworn"],
            "letter": ["dear sir", "dear madam", "letter of demand"],
            "invoice": ["invoice", "amount due", "subtotal"],
        }
        for doc_type, terms in signals.items():
            if sum(term in text for term in terms) >= 2:
                return doc_type
        return "unknown"
