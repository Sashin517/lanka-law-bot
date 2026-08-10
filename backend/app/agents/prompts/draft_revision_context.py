"""Context composition for full-document revision mode."""

from __future__ import annotations


def prepend_revision_context(
    context: str,
    existing_draft: str,
    revision_instruction: str,
) -> str:
    """Place the authoritative existing draft ahead of retrieved context."""

    return (
        "## REVISION MODE - Existing Draft to Revise\n\n"
        f"{existing_draft}\n\n"
        "## Revision Instruction\n\n"
        f"{revision_instruction}\n\n---\n\n"
        f"{context}"
    )
