"""Unsupported node — handles out-of-scope queries.

Returns a static response indicating the query falls outside the
supported Sri Lankan legal research scope.  Skips grounding
entirely (edges directly to formatter).
"""

from __future__ import annotations

import logging

from langsmith import traceable

from app.agents.state import AgentState

logger = logging.getLogger(__name__)


@traceable(name="UnsupportedNode")
async def unsupported_node(state: AgentState) -> dict:
    """Return a polite rejection for unsupported queries."""

    logger.info("Unsupported route triggered for: '%s'", state.question[:80])

    return {
        "summary": (
            "This query is outside the supported Sri Lankan legal "
            "research scope for the current system."
        ),
        "analysis": [],
        "retrieved_sources": [],
        "confidence": "low",
    }
