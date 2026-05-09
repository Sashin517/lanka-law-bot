from pydantic import BaseModel, Field

class LegalQuery(BaseModel):
    """Incoming search request from the frontend."""
    question: str = Field(min_length=1)
    document_ids: list[str] = Field(default_factory=list)
    matter_id: str | None = None
    doc_type: str | None = None
    start_year: int | None = None
