"""Pydantic models for the ingestion pipeline (used when building the vector store)."""

from __future__ import annotations

from pydantic import BaseModel


class ChunkMetadata(BaseModel):
    """Metadata attached to every parent and child chunk stored in Pinecone."""
    # Common
    source_type: str # "act" | "ordinance" | "case_law"
    doc_type: str
    jurisdiction: str = "Sri Lanka"
    subject_area: str
    source_filename: str
    keywords: list[str] = []
    
    # Chunk tracking
    chunk_id: str
    parent_id: str | None = None
    chunk_type: str # "parent" | "child" | "section_summary"
    section: str | None = None
    breadcrumb: str | None = None
    heading_path: list[str] = []
    text_hash: str
    
    # Acts/Ordinances
    title: str | None = None
    short_title: str | None = None
    act_number: int | None = None
    year: int = 0
    ordinance_numbers: list[str] = []
    act_numbers: list[str] = []
    date_certified: str | None = None
    date_enacted: str | None = None
    parent_act: str | None = None
    
    # Case Laws
    case_name: str | None = None
    plaintiff: str | None = None
    defendant: str | None = None
    court: str | None = None
    case_number: str | None = None
    lower_court_number: str | None = None
    date_decided: str | None = None
    date_heard: list[str] = []
    reporter_citation: str | None = None
    reporter_volume: str | None = None
    reporter_page: int | None = None
    judges: list[str] = []
    cases_cited: list[str] = []
    statutes_cited: list[str] = []
    legal_principles: list[str] = []
