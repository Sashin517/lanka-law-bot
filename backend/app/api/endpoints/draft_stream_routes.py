"""Streaming counterpart to the existing legal-draft edit endpoint.

``POST /api/draft/edit/stream`` uses the same deterministic light/heavy
classifier and application services as ``POST /api/draft/edit``. Streaming is
additive; existing response and error behavior remains available unchanged.
"""

from __future__ import annotations

import asyncio
import logging
from uuid import uuid4

from app.agents.streaming import ExecutionStreamManager, event_bus
from app.api.sse import stream_channel, streaming_response
from app.schemas.requests import DraftEditRequest
from app.services.generation.edit_classifier import classify_edit_complexity
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/edit/stream")
async def edit_draft_stream(request: DraftEditRequest) -> StreamingResponse:
    """Stream a targeted or structural draft edit and its final response."""

    session_id = str(uuid4())
    edit_path = classify_edit_complexity(
        instruction=request.instruction,
        selected_text=request.selected_text,
        current_content=request.current_content,
    )
    channel = event_bus.create_channel(session_id)
    stream_manager = ExecutionStreamManager(session_id, event_bus)

    logger.info(
        "SSE draft-edit stream created: session=%s draft_id=%s path=%s",
        session_id,
        request.draft_id,
        edit_path,
    )

    async def run_edit() -> None:
        from app.services.generation.draft_edit_service import (
            process_heavy_edit,
            process_light_edit,
        )

        try:
            stream_manager.emit_stream_start(
                request.instruction,
                f"edit_{edit_path}",
            )
            if edit_path == "heavy":
                stream_manager.emit_step_start(
                    "edit",
                    "Running full revision pipeline",
                )
                result = await process_heavy_edit(
                    request,
                    stream_emitter=stream_manager,
                )
                completion_label = "Full draft revision complete"
            else:
                stream_manager.emit_step_start("edit", "Applying targeted edit")
                result = await process_light_edit(
                    request,
                    stream_emitter=stream_manager,
                )
                completion_label = "Targeted draft edit complete"

            stream_manager.emit_step_done(
                "edit",
                completion_label,
                edit_path=edit_path,
            )
            stream_manager.emit_final(result.model_dump(mode="json"))
        except asyncio.CancelledError:
            logger.info("SSE draft-edit stream cancelled: session=%s", session_id)
            raise
        except Exception as exc:
            logger.exception("SSE draft edit failed: session=%s", session_id)
            stream_manager.emit_error(str(exc) or "Draft edit failed.")

    content = stream_channel(
        channel=channel,
        producer=run_edit,
        close_channel=lambda: event_bus.close_channel(session_id),
    )
    return streaming_response(content)
