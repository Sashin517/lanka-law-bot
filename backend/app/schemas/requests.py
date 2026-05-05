from pydantic import BaseModel, Field

class LegalQuery(BaseModel):
    """Incoming search request from the frontend."""
    question: str = Field(min_length=1)
