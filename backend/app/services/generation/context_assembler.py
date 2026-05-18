from __future__ import annotations

from langchain_core.documents import Document

from app.schemas.responses import SourceReference


class ContextAssembler:
    """Builds LLM-ready context with citation anchors from retrieval results."""

    def assemble(
        self,
        retrieval_results: list[dict],
    ) -> tuple[str, dict[str, SourceReference]]:

        context_parts: list[str] = []
        citation_map: dict[str, SourceReference] = {}

        for i, result in enumerate(retrieval_results, start=1):
            anchor = f"[{i}]"
            meta: dict = result["metadata"]

            # Prefer parent content; fall back to child
            parent = result.get("parent")
            child = result["child"]
            content = parent.page_content if parent else child.page_content

            # Build the header block that tells the LLM where this source is from
            title = meta.get("title", "Unknown Act")
            reference = meta.get("breadcrumb") or meta.get("source", "N/A")
            year = meta.get("year", "N/A")
            section = meta.get("section", "N/A")

            header = (
                f"--- Source {anchor} ---\n"
                f"Document: {title}\n"
                f"Reference: {reference}\n"
                f"Year: {year} | Section: {section}\n"
            )
            context_parts.append(f"{header}\n{content}\n")

            # Build the citation reference for the response payload.
            citation_map[anchor] = SourceReference(
                citation_id=anchor,
                title=title,
                section=meta.get("section"),
                year=int(year) if isinstance(year, (int, float)) else 0,
                breadcrumb=meta.get("breadcrumb"),
                excerpt=child.page_content[:300],
                content=content,
            )

        return "\n".join(context_parts), citation_map


class MultiSourceContextAssembler:
    """Build LLM-ready context while preserving law-vs-document boundaries."""

    def assemble(
        self,
        legal_results: list[dict],
        user_document_results: list[dict],
    ) -> tuple[str, dict[str, SourceReference]]:
        context_parts: list[str] = []
        citation_map: dict[str, SourceReference] = {}

        if legal_results:
            legal_context, legal_map = self._assemble_legal(legal_results)
            context_parts.append("## LEGAL AUTHORITY CONTEXT\n\n" + legal_context)
            citation_map.update(legal_map)

        if user_document_results:
            doc_context, doc_map = self._assemble_user_documents(user_document_results)
            context_parts.append("## USER DOCUMENT CONTEXT\n\n" + doc_context)
            citation_map.update(doc_map)

        return "\n\n".join(context_parts), citation_map

    def _assemble_legal(
        self,
        retrieval_results: list[dict],
    ) -> tuple[str, dict[str, SourceReference]]:
        context_parts: list[str] = []
        citation_map: dict[str, SourceReference] = {}

        for i, result in enumerate(retrieval_results, start=1):
            anchor = f"[LAW-{i}]"
            meta: dict = result["metadata"]
            content = self._result_content(result)

            title = meta.get("title", "Unknown Act")
            reference = meta.get("breadcrumb") or meta.get("source", "N/A")
            year = meta.get("year", "N/A")
            section = meta.get("section", "N/A")
            doc_type = meta.get("doc_type") or meta.get("document_type") or "legal_authority"

            context_parts.append(
                "\n".join(
                    [
                        f"--- Legal Source {anchor} ---",
                        f"Document: {title}",
                        f"Authority Type: {doc_type}",
                        f"Reference: {reference}",
                        f"Year: {year} | Section: {section}",
                        "Text:",
                        content,
                    ]
                )
            )

            # Excerpt uses the CHILD chunk (the semantically matched text),
            child_text = result["child"].page_content
            citation_map[anchor] = SourceReference(
                citation_id=anchor,
                title=title,
                section=meta.get("section"),
                year=int(year) if isinstance(year, (int, float)) else 0,
                breadcrumb=meta.get("breadcrumb"),
                excerpt=child_text[:300],
                content=content,
                source_type="legal_authority",
            )

        return "\n\n".join(context_parts), citation_map

    def _assemble_user_documents(
        self,
        retrieval_results: list[dict],
    ) -> tuple[str, dict[str, SourceReference]]:
        context_parts: list[str] = []
        citation_map: dict[str, SourceReference] = {}

        for i, result in enumerate(retrieval_results, start=1):
            anchor = f"[DOC-{i}]"
            meta: dict = result["metadata"]
            content = self._result_content(result)

            filename = meta.get("filename", "Uploaded document")
            heading_path = meta.get("heading_path") or []
            if isinstance(heading_path, list):
                heading = " > ".join(str(part) for part in heading_path if part)
            else:
                heading = str(heading_path)
            clause = meta.get("clause_label") or "N/A"

            context_parts.append(
                "\n".join(
                    [
                        f"--- User Document Source {anchor} ---",
                        f"Filename: {filename}",
                        f"Document ID: {meta.get('document_id', 'N/A')}",
                        f"Document Type: {meta.get('document_type', 'unknown')}",
                        f"Heading: {heading or 'N/A'}",
                        f"Clause: {clause}",
                        "Text:",
                        content,
                    ]
                )
            )

            child_text = result["child"].page_content
            citation_map[anchor] = SourceReference(
                citation_id=anchor,
                title=filename,
                section=clause if clause != "N/A" else None,
                year=0,
                breadcrumb=heading or None,
                excerpt=child_text[:300],
                content=content,
                source_type="user_document",
                document_id=meta.get("document_id"),
                filename=filename,
            )

        return "\n\n".join(context_parts), citation_map

    @staticmethod
    def _result_content(result: dict) -> str:
        parent: Document | None = result.get("parent")
        child: Document = result["child"]
        return parent.page_content if parent else child.page_content
