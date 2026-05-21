"""Formatter node — builds the final API response dict from agent state.

This is the last node before END.  It converts the internal
``AgentState`` fields into the JSON structure the frontend expects,
including route metadata, markdown content, sources, and grounding info.
"""

from __future__ import annotations

import logging

from langsmith import traceable

from app.agents.state import AgentState

logger = logging.getLogger(__name__)


@traceable(name="FormatterNode")
async def formatter_node(state: AgentState) -> dict:
    """Assemble ``final_response`` from the current state."""

    # Build route metadata for diagnostics
    route_dict = {
        "route": state.route,
        "task_type": state.task_type,
        "answer_mode": state.answer_mode,
        "target_corpus": state.target_corpus,
        "confidence": state.route_confidence,
        "needs_clarification": state.needs_clarification,
        "clarification_question": state.clarification_question,
    }

    final = {
        "route": route_dict,
        "answer": state.summary,                     # Plain text fallback
        "markdown_content": state.markdown_content,   # Rich markdown for rendering
        "sources": [src.model_dump() for src in state.retrieved_sources],
        "confidence": state.confidence,
        "grounding_score": state.grounding.grounding_score,
        "disclaimer": state.disclaimer,
        "draft_documents": state.draft_documents,
        "draft_document": state.draft_documents[0] if state.draft_documents else None,
        "draft_title": state.draft_title,
        "draft_document_type": state.draft_document_type,
        "sources_used": state.sources_used,
        "requires_completion": state.requires_completion,
        "section_map": state.section_map,
        "change_summary": state.change_summary,
    }

    logger.info(
        "Response formatted: %d sources, confidence=%s, grounding=%.2f, markdown=%d chars.",
        len(state.retrieved_sources),
        state.confidence,
        state.grounding.grounding_score,
        len(state.markdown_content),
    )

    return {"final_response": final}
