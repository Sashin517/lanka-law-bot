from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class QueryMode(str, Enum):
    """Explicit user-selected query mode.

    Sent from the frontend via mode-selector buttons.
    Replaces the previous LLM-based SemanticIntentRouter.
    """

    QUICK_QA = "quick_qa"
    DEEP_RESEARCH = "deep_research"
    DRAFTING = "drafting"
    REVIEW = "review"
    REASONING = "reasoning"


class LegalQuery(BaseModel):
    """Incoming search request from the frontend."""

    question: str = Field(min_length=1)
    mode: QueryMode = QueryMode.QUICK_QA
    document_ids: list[str] = Field(default_factory=list)
    matter_id: str | None = None
