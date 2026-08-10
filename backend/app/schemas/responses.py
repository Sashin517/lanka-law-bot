from __future__ import annotations
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

class CitedClaim(BaseModel):
    """A single legal statement with source citation references."""
    statement: str = Field(..., description="A factual legal claim grounded in the source documents.")
    citation_ids: list[str] = Field(default_factory=list, description='Source anchors referenced, e.g. ["[1]", "[3]"].')


class SourceReference(BaseModel):
    """A source document referenced in a generated response."""
    citation_id: str
    title: str
    section: str | None = None
    year: int = 0
    breadcrumb: str | None = None
    excerpt: str = ""
    content: str = Field(default="", exclude=True)
    source_type: str | None = None
    document_id: str | None = None
    filename: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    source_uri: str | None = None
    court: str | None = None
    reporter_citation: str | None = None
    docket_number: str | None = None
    authoritative: bool | None = None


class ConfidenceLevel(str, Enum):
    """Confidence level of the generated response."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RouteMetadata(BaseModel):
    """Public route metadata for query understanding diagnostics."""

    route: str
    task_type: str
    answer_mode: str
    target_corpus: str
    confidence: str
    needs_clarification: bool = False
    clarification_question: str | None = None


class LegalResponse(BaseModel):
    """Complete structured response from the RAG pipeline."""
    summary: str = Field(..., description="2-3 sentence direct answer with key citations.")
    analysis: list[CitedClaim] = Field(default_factory=list, description="Detailed breakdown of legal claims with citations.")
    sources: list[SourceReference] = Field(default_factory=list, description="All source documents referenced in the response.")
    confidence: str = ConfidenceLevel.MEDIUM
    route: RouteMetadata | None = None
    disclaimer: str = "This information is for research purposes only and does not constitute legal advice. Please consult a qualified legal professional for specific legal matters."


class ImprovePromptResponse(BaseModel):
    """Response payload for improved prompt suggestions."""

    improved_prompt: str
    intent_summary: str | None = None


class DraftEditResponse(BaseModel):
    """Edited document content returned by either draft-edit path."""

    edit_type: Literal["replace", "insert", "full_rewrite"]
    original_text: str
    edited_text: str
    markdown_content: str
    sources: list[SourceReference] = Field(default_factory=list)
    edit_summary: str
    confidence: Literal["high", "medium", "low"] = "medium"
    edit_path: Literal["light", "heavy"] = "light"
    execution_trace: dict[str, Any] | None = None


class DraftVersionSnapshot(BaseModel):
    """An immutable document snapshot in the draft version chain."""

    id: str = Field(min_length=1, max_length=128)
    draft_id: str = Field(min_length=1, max_length=128)
    version_number: int = Field(ge=1)
    content_json: dict[str, Any]
    content_markdown: str
    sources: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str
    created_by: Literal["ai", "user"]
    edit_summary: str
    parent_version_id: str | None = Field(default=None, max_length=128)
