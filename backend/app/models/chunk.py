from __future__ import annotations
from pydantic import BaseModel

class ChunkMetadata(BaseModel):
    """Metadata attached to every parent and child chunk stored in ChromaDB."""
    source: str
    doc_type: str = "Act"
    year: int
    act_number: int
    title: str = "Unknown Act"
    section: str | None = None
    breadcrumb: str | None = None
    topic: str | None = None
    jurisdiction: str = "Sri Lanka"
    citation_id: str
    chunk_type: str = "child"
    parent_id: str | None = None
