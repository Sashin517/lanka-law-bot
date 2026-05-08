from __future__ import annotations
from enum import Enum
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
    routing_reason: str = ""


class LegalResponse(BaseModel):
    """Complete structured response from the RAG pipeline."""
    summary: str = Field(..., description="2-3 sentence direct answer with key citations.")
    analysis: list[CitedClaim] = Field(default_factory=list, description="Detailed breakdown of legal claims with citations.")
    sources: list[SourceReference] = Field(default_factory=list, description="All source documents referenced in the response.")
    confidence: str = ConfidenceLevel.MEDIUM
    route: RouteMetadata | None = None
    disclaimer: str = "This information is for research purposes only and does not constitute legal advice. Please consult a qualified legal professional for specific legal matters."
