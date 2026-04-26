from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field


class ChunkMetadata(BaseModel):
    """Metadata attached to every parent and child chunk stored in ChromaDB."""

    source: str                                     # "Year_1995_Act_21.json"
    doc_type: str = "Act"                           # "Act" | "CaseLaw" | "Regulation"
    year: int                                       # 1995
    act_number: int                                 # 21
    title: str = "Unknown Act"                      # "Rent (Amendment) Act, No. 26 of 2002"
    section: str | None = None                      # "Section 12" (if parseable)
    breadcrumb: str | None = None                   # "Rent Act > Chapter III > Section 12"
    topic: str | None = None                        # Keyword-derived topic category
    jurisdiction: str = "Sri Lanka"
    citation_id: str                                # "act_1995_21_c3" (unique per chunk)
    chunk_type: str = "child"                       # "parent" | "child"
    parent_id: str | None = None                    # Links child → parent (None for parents)


class LegalQuery(BaseModel):
    """Incoming search request from the frontend."""
    question: str


class CitedClaim(BaseModel):
    """A single legal statement with source citation references."""

    statement: str = Field(
        ..., description="A factual legal claim grounded in the source documents."
    )
    citation_ids: list[str] = Field(
        default_factory=list,
        description='Source anchors referenced, e.g. ["[1]", "[3]"].',
    )


class SourceReference(BaseModel):
    """A source document referenced in a generated response."""

    citation_id: str                                # "[1]"
    title: str                                      # "Rent (Amendment) Act, No. 26 of 2002"
    section: str | None = None                      # "Section 12"
    year: int = 0
    breadcrumb: str | None = None                   # "Rent Act > Chapter III > Section 12"
    excerpt: str = ""                               # First 200 chars of the source chunk


class ConfidenceLevel(str, Enum):
    """Confidence level of the generated response."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class LegalResponse(BaseModel):
    """Complete structured response from the RAG pipeline."""

    summary: str = Field(
        ..., description="2-3 sentence direct answer with key citations."
    )
    analysis: list[CitedClaim] = Field(
        default_factory=list,
        description="Detailed breakdown of legal claims with citations.",
    )
    sources: list[SourceReference] = Field(
        default_factory=list,
        description="All source documents referenced in the response.",
    )
    confidence: str = ConfidenceLevel.MEDIUM
    disclaimer: str = (
        "This information is for research purposes only and does not "
        "constitute legal advice. Please consult a qualified legal "
        "professional for specific legal matters."
    )
