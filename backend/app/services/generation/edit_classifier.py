"""Deterministic complexity routing for document-edit requests.

The classifier deliberately performs no network or model calls. This keeps
localized edits fast while routing structural, research-heavy work through the
full multi-agent graph.
"""

from __future__ import annotations

from typing import Literal


EditPath = Literal["light", "heavy"]

_HEAVY_SIGNALS = tuple(
    signal.casefold()
    for signal in (
        "rewrite",
        "restructure",
        "overhaul",
        "redo",
        "rebuild",
        "align with",
        "comply with",
        "compliance",
        "conform to",
        "entire document",
        "whole document",
        "all sections",
        "all clauses",
        "based on recent",
        "recent amendments",
        "latest case law",
        "incorporate",
        "comprehensive revision",
        "full revision",
        "research",
        "analyze the impact",
        "analyse the impact",
        "Supreme Court",
        "Court of Appeal",
        "multiple acts",
        "all relevant",
        "thorough review and rewrite",
    )
)
_DOCUMENT_WIDE_SIGNALS = (
    "entire",
    "whole",
    "all",
    "every section",
    "throughout",
    "document",
    "draft",
)
_LIGHT_MAX_SELECTION_CHARS = 2_000


def classify_edit_complexity(
    instruction: str,
    selected_text: str | None,
    current_content: str,
) -> EditPath:
    """Classify a requested edit as a localized or full-pipeline operation.

    ``current_content`` is retained in the public contract because future
    classifiers may use document size or structure. The current deterministic
    rules intentionally depend only on the instruction and selection.
    """

    del current_content
    normalized_instruction = instruction.casefold()
    has_heavy_signal = any(
        signal in normalized_instruction for signal in _HEAVY_SIGNALS
    )

    if selected_text and len(selected_text) <= _LIGHT_MAX_SELECTION_CHARS:
        if not has_heavy_signal:
            return "light"

    if has_heavy_signal:
        return "heavy"

    if not selected_text and any(
        signal in normalized_instruction for signal in _DOCUMENT_WIDE_SIGNALS
    ):
        return "heavy"

    if selected_text and len(selected_text) > _LIGHT_MAX_SELECTION_CHARS:
        return "heavy"

    return "light"
