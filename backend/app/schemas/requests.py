from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator


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


class ImprovePromptRequest(BaseModel):
    """Request body for prompt refinement endpoint."""

    draft: str = Field(min_length=1, max_length=4000)
    mode: QueryMode = QueryMode.QUICK_QA
    has_documents: bool = False


class DraftEditRequest(BaseModel):
    """A document edit request handled by the unified light/heavy pipeline."""

    draft_id: str = Field(min_length=1, max_length=64)
    instruction: str = Field(min_length=1, max_length=12000)
    selected_text: str | None = None
    selection_start: int | None = Field(default=None, ge=0)
    selection_end: int | None = Field(default=None, ge=0)
    current_content: str = Field(max_length=2_000_000)
    document_ids: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("draft_id", "instruction")
    @classmethod
    def reject_blank_values(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("selected_text")
    @classmethod
    def normalize_empty_selection(cls, value: str | None) -> str | None:
        return value if value and value.strip() else None

    @model_validator(mode="after")
    def validate_selection_range(self) -> "DraftEditRequest":
        if (self.selection_start is None) != (self.selection_end is None):
            raise ValueError("selection_start and selection_end must be provided together")
        if (
            self.selection_start is not None
            and self.selection_end is not None
            and self.selection_start > self.selection_end
        ):
            raise ValueError("selection_start must not exceed selection_end")
        return self
