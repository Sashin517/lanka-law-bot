"""API endpoints for legal query processing.

Uses the LangGraph multi-agent system as the primary pipeline.
Falls back to the monolithic ``app.agent`` orchestrator if the
graph is unavailable (safety net during migration).
"""

import logging
from fastapi import APIRouter

from app.schemas.requests import LegalQuery
from app.agents.graph import build_graph
from app.agents.state import AgentState

logger = logging.getLogger(__name__)

router = APIRouter()

# Compile the graph once at module load
_graph = build_graph()


@router.get("/")
def read_root():
    """Health check endpoint."""
    return {"status": "LankaLawBot Backend is running!"}


@router.post("/search")
async def search_law(query: LegalQuery):
    """Process a legal query through the multi-agent graph.

    The graph handles: routing → worker agent → grounding → formatting.
    The formatter node builds ``final_response`` which is returned directly.
    """
    logger.info("Received query: '%s'", query.question[:100])

    # Build initial state from the request
    initial_state = AgentState(
        question=query.question,
        mode=query.mode.value,
        document_ids=query.document_ids or [],
        matter_id=query.matter_id,
    )

    # Run the multi-agent graph
    final_state = await _graph.ainvoke(initial_state.model_dump())

    # The formatter node puts the API-ready dict in final_response
    if final_state.get("final_response"):
        return final_state["final_response"]

    # Safety fallback — should not reach here if graph is wired correctly
    logger.warning("Graph did not produce final_response. Returning raw state.")
    return {
        "route": {"route": final_state.get("route", "unknown")},
        "answer": final_state.get("summary", "An error occurred."),
        "results": [],
        "analysis": [],
        "sources": [],
        "confidence": final_state.get("confidence", "low"),
        "grounding_score": 0.0,
        "disclaimer": final_state.get("disclaimer", ""),
    }
