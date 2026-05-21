from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.services.document_converter import DocumentConverter


@dataclass(frozen=True)
class AppliedDraftOperation:
    operation_type: str
    target: dict[str, Any]
    before_text: str
    after_text: str
    rationale: str


@dataclass(frozen=True)
class AppliedDraftOperationSet:
    markdown_content: str
    editor_json: dict[str, Any]
    html_content: str
    change_summary: str
    sources_used: list[str]
    changes: list[AppliedDraftOperation]


class AgentEditOperationService:
    """Applies structured agent operations deterministically.

    Agents describe intent in operations; this service owns the actual document
    mutation so raw editor JSON is not patched directly by an LLM.
    """

    def __init__(self, converter: DocumentConverter | None = None) -> None:
        self.converter = converter or DocumentConverter()

    def apply_operations(
        self,
        current_markdown: str,
        operation_set: dict[str, Any],
    ) -> AppliedDraftOperationSet:
        markdown = current_markdown
        applied: list[AppliedDraftOperation] = []

        for raw_operation in operation_set.get("operations", []):
            operation_type = raw_operation.get("type", "")
            target = raw_operation.get("target") or {}
            rationale = raw_operation.get("rationale", "")

            if operation_type == "replace_section":
                replacement = raw_operation.get("replacement_markdown", "")
                markdown, change = self._replace_section(
                    markdown=markdown,
                    target=target,
                    replacement_markdown=replacement,
                    rationale=rationale,
                )
                applied.append(change)

        editor_json = self.converter.markdown_to_tiptap_json(markdown)
        return AppliedDraftOperationSet(
            markdown_content=markdown,
            editor_json=editor_json,
            html_content=self.converter.markdown_to_html(markdown),
            change_summary=operation_set.get("change_summary", "Agent applied draft operations."),
            sources_used=list(operation_set.get("sources_used", [])),
            changes=applied,
        )

    def operation_set_from_revised_markdown(
        self,
        current_markdown: str,
        revised_markdown: str,
        instruction: str,
        section_ids: list[str],
        sources_used: list[str],
    ) -> dict[str, Any]:
        target_heading = section_ids[0] if section_ids else ""
        if target_heading:
            replacement = self._extract_section(revised_markdown, target_heading) or revised_markdown
            operation = {
                "type": "replace_section",
                "target": {"section_heading": target_heading},
                "replacement_markdown": replacement,
                "rationale": instruction,
            }
        else:
            operation = {
                "type": "replace_section",
                "target": {"section_heading": ""},
                "replacement_markdown": revised_markdown or current_markdown,
                "rationale": instruction,
            }

        return {
            "operations": [operation],
            "change_summary": f"Agent edit: {instruction}",
            "sources_used": sources_used,
        }

    def _replace_section(
        self,
        markdown: str,
        target: dict[str, Any],
        replacement_markdown: str,
        rationale: str,
    ) -> tuple[str, AppliedDraftOperation]:
        heading = str(target.get("section_heading") or "").strip()
        replacement = replacement_markdown.strip()

        if not heading:
            return (
                replacement or markdown,
                AppliedDraftOperation(
                    operation_type="replace_section",
                    target=target,
                    before_text=markdown,
                    after_text=replacement or markdown,
                    rationale=rationale,
                ),
            )

        bounds = self._find_section_bounds(markdown, heading)
        if not bounds:
            separator = "\n\n" if markdown.strip() else ""
            after = f"{markdown.rstrip()}{separator}{replacement}".strip()
            return (
                after,
                AppliedDraftOperation(
                    operation_type="replace_section",
                    target=target,
                    before_text="",
                    after_text=replacement,
                    rationale=rationale,
                ),
            )

        start, end = bounds
        before_text = markdown[start:end].strip()
        after = f"{markdown[:start].rstrip()}\n\n{replacement}\n\n{markdown[end:].lstrip()}".strip()
        return (
            after,
            AppliedDraftOperation(
                operation_type="replace_section",
                target=target,
                before_text=before_text,
                after_text=replacement,
                rationale=rationale,
            ),
        )

    def _find_section_bounds(self, markdown: str, heading: str) -> tuple[int, int] | None:
        pattern = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
        normalized = self._normalize_heading(heading)
        matches = list(pattern.finditer(markdown))
        for index, match in enumerate(matches):
            if self._normalize_heading(match.group(2)) != normalized:
                continue
            level = len(match.group(1))
            end = len(markdown)
            for next_match in matches[index + 1 :]:
                if len(next_match.group(1)) <= level:
                    end = next_match.start()
                    break
            return match.start(), end
        return None

    def _extract_section(self, markdown: str, heading: str) -> str:
        bounds = self._find_section_bounds(markdown, heading)
        if not bounds:
            return ""
        start, end = bounds
        return markdown[start:end].strip()

    def _first_heading(self, markdown: str) -> str:
        match = re.search(r"^#{1,6}\s+(.+?)\s*$", markdown, flags=re.MULTILINE)
        return match.group(1).strip() if match else ""

    def _normalize_heading(self, heading: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", heading.lower())
