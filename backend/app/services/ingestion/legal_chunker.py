from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid5, NAMESPACE_URL

from app.core.config import settings
from app.schemas.documents import UserDocumentMetadata


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
CLAUSE_RE = re.compile(
    r"^\s*("
    r"(?:clause|section|article|schedule|annexure|recital)\s+[\w().-]+(?:\s+.{0,120})?"
    r"|\d+(?:\.\d+)*\.?(?:\s+.{0,120})?"
    r"|\([a-zA-Z0-9]+\)(?:\s+.{0,120})?"
    r")",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class LegalChunk:
    id: str
    text: str
    metadata: UserDocumentMetadata


@dataclass(frozen=True)
class ChunkSet:
    chunks: list[LegalChunk] = field(default_factory=list)

    @property
    def vectorized_chunks(self) -> list[LegalChunk]:
        return [chunk for chunk in self.chunks if chunk.text.strip()]


@dataclass(frozen=True)
class ChunkingDocumentContext:
    tenant_id: str
    user_id: str
    matter_id: str | None
    document_id: str
    filename: str
    file_hash: str
    document_type: str


class LegalDocumentChunker:
    def chunk(self, markdown: str, context: ChunkingDocumentContext) -> ChunkSet:
        sections = self._split_by_structure(markdown)
        chunks: list[LegalChunk] = []

        for section_index, section in enumerate(sections):
            parent_text = section["text"].strip()
            if not parent_text:
                continue
            for parent_part_index, parent_part in enumerate(
                self._window_text(
                    parent_text,
                    settings.USER_PARENT_CHUNK_SIZE,
                    settings.USER_PARENT_CHUNK_OVERLAP,
                )
            ):
                parent_id = self._chunk_id(
                    context.document_id,
                    "parent",
                    section_index,
                    parent_part_index,
                    parent_part,
                )
                chunks.append(
                    self._make_chunk(
                        chunk_id=parent_id,
                        text=parent_part,
                        context=context,
                        heading_path=section["heading_path"],
                        clause_label=section["clause_label"],
                        chunk_type="parent",
                        chunk_strategy=section["strategy"],
                        parent_id=None,
                    )
                )

                child_parts = self._window_text(
                    parent_part,
                    settings.USER_CHILD_CHUNK_SIZE,
                    settings.USER_CHILD_CHUNK_OVERLAP,
                )
                for child_index, child_text in enumerate(child_parts):
                    child_id = self._chunk_id(
                        context.document_id,
                        "child",
                        section_index,
                        child_index,
                        child_text,
                    )
                    chunks.append(
                        self._make_chunk(
                            chunk_id=child_id,
                            text=child_text,
                            context=context,
                            heading_path=section["heading_path"],
                            clause_label=section["clause_label"],
                            chunk_type="child",
                            chunk_strategy="parent_child",
                            parent_id=parent_id,
                        )
                    )

                summary = self._extractive_summary(parent_part, section["heading_path"])
                if summary:
                    summary_id = self._chunk_id(
                        context.document_id,
                        "summary",
                        section_index,
                        parent_part_index,
                        summary,
                    )
                    chunks.append(
                        self._make_chunk(
                            chunk_id=summary_id,
                            text=summary,
                            context=context,
                            heading_path=section["heading_path"],
                            clause_label=section["clause_label"],
                            chunk_type="section_summary",
                            chunk_strategy="extractive_summary",
                            parent_id=parent_id,
                        )
                    )

        return ChunkSet(chunks=chunks)

    def _split_by_structure(self, markdown: str) -> list[dict]:
        blocks = self._protect_tables(markdown)
        sections: list[dict] = []
        current_lines: list[str] = []
        heading_path: list[str] = []
        current_clause: str | None = None
        current_strategy = "markdown_heading"

        def flush() -> None:
            text = "\n".join(current_lines).strip()
            if text:
                sections.append(
                    {
                        "text": text,
                        "heading_path": heading_path.copy(),
                        "clause_label": current_clause,
                        "strategy": current_strategy,
                    }
                )

        for block in blocks:
            if block.startswith("|"):
                current_lines.append(block)
                continue

            for line in block.splitlines():
                heading_match = HEADING_RE.match(line)
                clause_match = CLAUSE_RE.match(line)
                if heading_match:
                    flush()
                    current_lines = [line]
                    level = len(heading_match.group(1))
                    title = heading_match.group(2).strip()
                    heading_path = heading_path[: level - 1] + [title]
                    current_clause = None
                    current_strategy = "markdown_heading"
                elif clause_match and len("\n".join(current_lines)) > 350:
                    flush()
                    current_lines = [line]
                    current_clause = clause_match.group(1).strip()[:120]
                    current_strategy = "legal_clause"
                else:
                    current_lines.append(line)

        flush()
        if sections:
            return sections
        return [
            {
                "text": markdown,
                "heading_path": [],
                "clause_label": None,
                "strategy": "fallback_recursive",
            }
        ]

    @staticmethod
    def _protect_tables(markdown: str) -> list[str]:
        blocks: list[str] = []
        current_table: list[str] = []
        current_text: list[str] = []

        def flush_text() -> None:
            if current_text:
                blocks.append("\n".join(current_text))
                current_text.clear()

        def flush_table() -> None:
            if current_table:
                flush_text()
                blocks.append("\n".join(current_table))
                current_table.clear()

        for line in markdown.splitlines():
            if "|" in line and line.count("|") >= 2:
                current_table.append(line)
            else:
                flush_table()
                current_text.append(line)
        flush_table()
        flush_text()
        return blocks

    @staticmethod
    def _window_text(text: str, size: int, overlap: int) -> list[str]:
        clean = re.sub(r"\n{3,}", "\n\n", text).strip()
        if len(clean) <= size:
            return [clean]
        parts: list[str] = []
        start = 0
        while start < len(clean):
            end = min(start + size, len(clean))
            if end < len(clean):
                boundary = max(clean.rfind("\n\n", start, end), clean.rfind(". ", start, end))
                if boundary > start + int(size * 0.55):
                    end = boundary + 1
            parts.append(clean[start:end].strip())
            if end >= len(clean):
                break
            start = max(end - overlap, start + 1)
        return [part for part in parts if part]

    @staticmethod
    def _extractive_summary(text: str, heading_path: list[str]) -> str | None:
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        summary_sentences = [sentence for sentence in sentences if sentence][:2]
        if not summary_sentences and not heading_path:
            return None
        heading = " > ".join(heading_path)
        body = " ".join(summary_sentences)
        return f"{heading}\n{body}".strip()

    def _make_chunk(
        self,
        chunk_id: str,
        text: str,
        context: ChunkingDocumentContext,
        heading_path: list[str],
        clause_label: str | None,
        chunk_type: str,
        chunk_strategy: str,
        parent_id: str | None,
    ) -> LegalChunk:
        text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        metadata = UserDocumentMetadata(
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            matter_id=context.matter_id,
            document_id=context.document_id,
            filename=context.filename,
            file_hash=context.file_hash,
            document_type=context.document_type,
            heading_path=heading_path,
            clause_label=clause_label,
            chunk_id=chunk_id,
            parent_id=parent_id,
            chunk_type=chunk_type,  # type: ignore[arg-type]
            chunk_strategy=chunk_strategy,
            text_hash=text_hash,
            embedding_model=settings.PINECONE_EMBEDDING_MODEL,
            embedding_dimension=settings.PINECONE_EMBEDDING_DIMENSION,
            created_at=datetime.utcnow().isoformat(),
        )
        return LegalChunk(id=chunk_id, text=text, metadata=metadata)

    @staticmethod
    def _chunk_id(
        document_id: str,
        chunk_type: str,
        section_index: int,
        chunk_index: int,
        text: str,
    ) -> str:
        text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
        return str(uuid5(NAMESPACE_URL, f"{document_id}:{chunk_type}:{section_index}:{chunk_index}:{text_hash}"))
