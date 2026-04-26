from pydantic import BaseModel

class LegalQuery(BaseModel):
    """Incoming search request from the frontend."""
    question: str
