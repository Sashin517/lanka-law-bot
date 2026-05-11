"""Formatter node — builds the final API response dict from agent state.

This is the last node before END.  It converts the internal
``AgentState`` fields into the JSON structure the frontend expects,
including route metadata, answer, analysis, sources, and grounding info.
"""

from __future__ import annotations

import logging

from langsmith import traceable

from app.agents.state import AgentState

logger = logging.getLogger(__name__)


@traceable(name="FormatterNode")
async def formatter_node(state: AgentState) -> dict:
    """Assemble ``final_response`` from the current state."""

    # Build the "results" array the frontend uses for source cards
    results = []
    for i, source in enumerate(state.retrieved_sources):
        results.append({
            "id": source.citation_id or f"source-{i}",
            "title": source.title or "Unknown Act",
            "subtitle": f"Year: {source.year} | {source.section or 'N/A'}",
            "excerpt": source.excerpt or "",
            "score": state.confidence,
        })

    # Build the route metadata dict
    route_dict = {
        "route": state.route,
        "task_type": state.task_type,
        "answer_mode": state.answer_mode,
        "target_corpus": state.target_corpus,
        "confidence": state.route_confidence,
        "needs_clarification": state.needs_clarification,
        "clarification_question": state.clarification_question,
        "routing_reason": state.routing_reason,
    }

    final = {
        "route": route_dict,
        "answer": state.summary,
        "results": results,
        "analysis": [
            {
                "statement": claim.statement,
                "citations": claim.citation_ids,
            }
            for claim in state.analysis
        ],
        "sources": [src.model_dump() for src in state.retrieved_sources],
        "confidence": state.confidence,
        "grounding_score": state.grounding.grounding_score,
        "disclaimer": state.disclaimer,
    }

    logger.info(
        "Response formatted: %d sources, %d claims, confidence=%s, grounding=%.2f",
        len(results),
        len(state.analysis),
        state.confidence,
        state.grounding.grounding_score,
    )

    return {"final_response": final}
