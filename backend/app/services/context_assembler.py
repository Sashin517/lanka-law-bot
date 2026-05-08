from __future__ import annotations

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

            # Build the citation reference for the response payload
            citation_map[anchor] = SourceReference(
                citation_id=anchor,
                title=title,
                section=meta.get("section"),
                year=int(year) if isinstance(year, (int, float)) else 0,
                breadcrumb=meta.get("breadcrumb"),
                excerpt=content[:200],
            )

        return "\n".join(context_parts), citation_map
