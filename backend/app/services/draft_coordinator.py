from __future__ import annotations

import re

from app.schemas.drafts import DraftDocumentSpec, GenerateDocumentsRequest


class DraftGenerationCoordinator:
    """Resolves one user prompt into concrete draft document specs."""

    _TYPE_PATTERNS: list[tuple[str, str, list[str]]] = [
        ("contract", "Contract", ["contract", "agreement", "lease"]),
        ("resolution", "Resolution", ["resolution", "board resolution"]),
        ("notice", "Notice", ["notice", "demand letter", "letter of demand"]),
        ("affidavit", "Affidavit", ["affidavit", "sworn statement"]),
        ("pleading", "Pleading", ["plaint", "petition", "pleading", "motion"]),
    ]

    def resolve_specs(self, request: GenerateDocumentsRequest) -> list[DraftDocumentSpec]:
        if request.document_specs:
            return request.document_specs

        specs = self._extract_specs_from_prompt(request.prompt)
        if specs:
            return specs

        return [
            DraftDocumentSpec(
                title="Generated Legal Draft",
                document_type="draft",
                instructions=request.prompt,
            )
        ]

    def compose_generation_question(
        self,
        prompt: str,
        spec: DraftDocumentSpec,
    ) -> str:
        parts = [
            prompt.strip(),
            f"Document type: {spec.document_type or 'draft'}",
            f"Title: {spec.title}",
        ]
        if spec.instructions.strip():
            parts.append(f"Specific instructions: {spec.instructions.strip()}")
        return "\n\n".join(parts)

    def _extract_specs_from_prompt(self, prompt: str) -> list[DraftDocumentSpec]:
        text = prompt.lower()
        specs: list[DraftDocumentSpec] = []
        seen: set[str] = set()

        for document_type, title_suffix, patterns in self._TYPE_PATTERNS:
            for pattern in patterns:
                if re.search(rf"\b{re.escape(pattern)}s?\b", text):
                    key = f"{document_type}:{pattern}"
                    if key in seen:
                        continue
                    seen.add(key)
                    specs.append(
                        DraftDocumentSpec(
                            document_type=document_type,
                            title=self._title_from_pattern(pattern, title_suffix),
                            instructions=f"Generate the {pattern} requested in the user prompt.",
                        )
                    )
                    break

        return specs

    def _title_from_pattern(self, pattern: str, fallback_suffix: str) -> str:
        cleaned = " ".join(part.capitalize() for part in pattern.split())
        if cleaned in {"Lease", "Agreement"}:
            return f"{cleaned} Agreement"
        return cleaned or fallback_suffix
