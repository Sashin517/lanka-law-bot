from __future__ import annotations

import html
import re
import zipfile
from datetime import datetime
from io import BytesIO
from typing import Any


class DocumentConverter:
    """Canonical conversions for editable draft documents.

    Tiptap/ProseMirror JSON is the persisted editor shape. Markdown stays the
    agent-facing fallback, and HTML/DOCX/PDF are export/render formats.
    """

    def markdown_to_tiptap_json(self, markdown: str) -> dict[str, Any]:
        content: list[dict[str, Any]] = []
        for block in re.split(r"\n{2,}", markdown.strip()):
            text = block.strip()
            if not text:
                continue
            heading = re.match(r"^(#{1,6})\s+(.+)$", text)
            if heading:
                content.append(
                    {
                        "type": "heading",
                        "attrs": {"level": len(heading.group(1))},
                        "content": [{"type": "text", "text": heading.group(2)}],
                    }
                )
            else:
                content.append(
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": text}],
                    }
                )
        return {"type": "doc", "content": content}

    def tiptap_json_to_markdown(self, editor_json: dict[str, Any]) -> str:
        blocks: list[str] = []
        for node in editor_json.get("content", []):
            node_type = node.get("type")
            text = self._node_text(node)
            if not text:
                continue
            if node_type == "heading":
                level = int(node.get("attrs", {}).get("level", 2))
                blocks.append(f"{'#' * max(1, min(level, 6))} {text}")
            elif node_type == "bulletList":
                blocks.extend(f"- {item}" for item in self._list_items(node))
            elif node_type == "orderedList":
                blocks.extend(
                    f"{index}. {item}" for index, item in enumerate(self._list_items(node), start=1)
                )
            else:
                blocks.append(text)
        return "\n\n".join(blocks)

    def tiptap_json_to_html(self, editor_json: dict[str, Any]) -> str:
        return self.markdown_to_html(self.tiptap_json_to_markdown(editor_json))

    def markdown_to_html(self, markdown: str) -> str:
        blocks: list[str] = []
        for block in re.split(r"\n{2,}", markdown.strip()):
            text = block.strip()
            if not text:
                continue
            heading = re.match(r"^(#{1,6})\s+(.+)$", text)
            if heading:
                level = len(heading.group(1))
                blocks.append(f"<h{level}>{html.escape(heading.group(2))}</h{level}>")
            else:
                escaped = html.escape(text).replace("\n", "<br>")
                blocks.append(f"<p>{escaped}</p>")
        return "\n".join(blocks)

    def html_to_pdf(self, title: str, html_content: str) -> bytes:
        text = re.sub(r"<[^>]+>", "\n", html_content)
        text = html.unescape(re.sub(r"\n{3,}", "\n\n", text)).strip()
        return self.markdown_to_pdf(title, text)

    def tiptap_json_to_docx(self, title: str, editor_json: dict[str, Any]) -> bytes:
        return self.markdown_to_docx(title, self.tiptap_json_to_markdown(editor_json))

    def html_to_docx(self, title: str, html_content: str) -> bytes:
        text = html.unescape(re.sub(r"<[^>]+>", "\n", html_content)).strip()
        return self.markdown_to_docx(title, text)

    def markdown_to_docx(self, title: str, markdown: str) -> bytes:
        text = html.escape(self._plain_text_from_markdown(markdown))
        paragraphs = "".join(
            f"<w:p><w:r><w:t>{line}</w:t></w:r></w:p>"
            for line in text.splitlines()
            if line.strip()
        )
        document_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f"<w:body>{paragraphs}<w:sectPr /></w:body></w:document>"
        )
        core_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" '
            'xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            f"<dc:title>{html.escape(title)}</dc:title>"
            f'<dcterms:created xsi:type="dcterms:W3CDTF">{datetime.utcnow().isoformat()}Z</dcterms:created>'
            "</cp:coreProperties>"
        )
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as docx:
            docx.writestr(
                "[Content_Types].xml",
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
                "</Types>",
            )
            docx.writestr(
                "_rels/.rels",
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
                '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
                "</Relationships>",
            )
            docx.writestr("word/document.xml", document_xml)
            docx.writestr("docProps/core.xml", core_xml)
        return buffer.getvalue()

    def markdown_to_pdf(self, title: str, markdown: str) -> bytes:
        text = f"{title}\n\n{self._plain_text_from_markdown(markdown)}"
        lines = [line[:90] for line in text.splitlines() if line.strip()][:45]
        stream_lines = ["BT", "/F1 11 Tf", "72 760 Td"]
        for index, line in enumerate(lines):
            escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            if index:
                stream_lines.append("0 -16 Td")
            stream_lines.append(f"({escaped}) Tj")
        stream_lines.append("ET")
        stream = "\n".join(stream_lines).encode("latin-1", errors="replace")
        objects = [
            b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
            b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n",
            b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n",
            b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n",
            f"5 0 obj << /Length {len(stream)} >> stream\n".encode("ascii")
            + stream
            + b"\nendstream endobj\n",
        ]
        output = BytesIO()
        output.write(b"%PDF-1.4\n")
        offsets = [0]
        for obj in objects:
            offsets.append(output.tell())
            output.write(obj)
        xref_offset = output.tell()
        output.write(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
        output.write(b"0000000000 65535 f \n")
        for offset in offsets[1:]:
            output.write(f"{offset:010d} 00000 n \n".encode("ascii"))
        output.write(
            f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF".encode(
                "ascii"
            )
        )
        return output.getvalue()

    def _node_text(self, node: dict[str, Any]) -> str:
        parts: list[str] = []
        for child in node.get("content", []):
            if child.get("type") == "text":
                parts.append(child.get("text", ""))
            else:
                parts.append(self._node_text(child))
        return "".join(parts).strip()

    def _list_items(self, node: dict[str, Any]) -> list[str]:
        return [
            self._node_text(item)
            for item in node.get("content", [])
            if self._node_text(item)
        ]

    def _plain_text_from_markdown(self, markdown: str) -> str:
        return re.sub(r"[*_`>#-]+", "", markdown).strip()
