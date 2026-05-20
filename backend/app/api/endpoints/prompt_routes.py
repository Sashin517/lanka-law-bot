"""API endpoints for query prompt improvement."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.schemas.requests import ImprovePromptRequest
from app.schemas.responses import ImprovePromptResponse
from app.services.generation.prompt_improvement_service import PromptImprovementService

logger = logging.getLogger(__name__)
router = APIRouter()
_service = PromptImprovementService()


@router.post("/improve", response_model=ImprovePromptResponse)
async def improve_prompt(body: ImprovePromptRequest) -> ImprovePromptResponse:
    """Improve a user draft prompt using mode-aware LLM guidance."""
    try:
        return await _service.improve(body.draft, body.mode, body.has_documents)
    except ValueError as exc:
        logger.warning("Prompt improvement validation failed: %s", exc)
        raise HTTPException(status_code=502, detail="Prompt improvement failed.") from exc
