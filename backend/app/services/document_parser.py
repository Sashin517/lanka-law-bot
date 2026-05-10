from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


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

        try:
            from docling.document_converter import DocumentConverter, PdfFormatOption
            from docling.datamodel.pipeline_options import PdfPipelineOptions, AcceleratorOptions
            from docling.datamodel.base_models import InputFormat
        except ImportError as exc:
            raise RuntimeError(
                "Docling is not installed. Install backend requirements before ingesting PDFs/DOCX."
            ) from exc

        pipeline_options = PdfPipelineOptions(
            accelerator_options=AcceleratorOptions(num_threads=1)
        )

        converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
            }
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
