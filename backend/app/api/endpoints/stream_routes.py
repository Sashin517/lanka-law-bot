"""Streaming counterpart to the existing legal-search endpoint.

``POST /api/search/stream`` executes the same LangGraph and produces the same
final response as ``POST /api/search`` while exposing typed execution activity
as Server-Sent Events. The legacy endpoint is intentionally untouched.
"""

from __future__ import annotations

import asyncio
import logging
from uuid import uuid4

from app.agents.runtime import get_graph
from app.agents.state import AgentState
from app.agents.streaming import ExecutionStreamManager, event_bus
from app.api.sse import stream_channel, streaming_response
from app.schemas.requests import LegalQuery
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langchain_core.runnables import RunnableConfig

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/search/stream")
async def search_law_stream(query: LegalQuery) -> StreamingResponse:
    """Stream graph activity followed by one complete legal-query response."""

    session_id = str(uuid4())
    channel = event_bus.create_channel(session_id)
    stream_manager = ExecutionStreamManager(session_id, event_bus)
    initial_state = AgentState(
        question=query.question,
        mode=query.mode.value,
        document_ids=query.document_ids or [],
        matter_id=query.matter_id,
        session_id=session_id,
    )
    graph_config: RunnableConfig = {"configurable": {"stream_emitter": stream_manager}}

    logger.info(
        "SSE search stream created: session=%s mode=%s question_len=%d",
        session_id,
        query.mode.value,
        len(query.question),
    )

    async def run_graph() -> None:
        try:
            stream_manager.emit_stream_start(query.question, query.mode.value)
            final_state = await get_graph().ainvoke(
                initial_state.model_dump(),
                config=graph_config,
            )
            final_response = final_state.get("final_response")
            if not final_response:
                logger.warning(
                    "Graph did not produce final_response: session=%s",
                    session_id,
                )
                # Match the existing /api/search safety response so the
                # streaming transport never changes application semantics.
                final_response = {
                    "route": {"route": final_state.get("route", "unknown")},
                    "answer": final_state.get("summary", "An error occurred."),
                    "results": [],
                    "analysis": [],
                    "sources": [],
                    "confidence": final_state.get("confidence", "low"),
                    "grounding_score": 0.0,
                    "disclaimer": final_state.get("disclaimer", ""),
                }
            if not stream_manager.final_emitted:
                # Defensive fallback for a custom graph that bypasses formatter.
                stream_manager.emit_final(final_response)
        except asyncio.CancelledError:
            logger.info("SSE search stream cancelled: session=%s", session_id)
            raise
        except Exception as exc:
            logger.exception("SSE graph execution failed: session=%s", session_id)
            stream_manager.emit_error(str(exc) or "Graph execution failed.")

    content = stream_channel(
        channel=channel,
        producer=run_graph,
        close_channel=lambda: event_bus.close_channel(session_id),
    )
    return streaming_response(content)
