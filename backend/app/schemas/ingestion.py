"""Pydantic models for the ingestion pipeline (used when building the vector store)."""

from __future__ import annotations

from pydantic import BaseModel


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
