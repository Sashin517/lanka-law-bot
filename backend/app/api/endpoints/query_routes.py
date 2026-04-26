import logging
from fastapi import APIRouter

from app.schemas.requests import LegalQuery
from app.agent import process_legal_query

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/")
def read_root():
    """Health check endpoint."""
    return {"status": "LankaLawBot Backend is running!"}


@router.post("/search")
async def search_law(query: LegalQuery):
    logger.info("Received query: '%s'", query.question[:100])

    response = await process_legal_query(query.question)

    return {
        "answer": response.summary,
        "analysis": [
            {
                "statement": claim.statement,
                "citations": claim.citation_ids,
            }
            for claim in response.analysis
        ],
        "sources": [source.model_dump() for source in response.sources],
        "confidence": response.confidence,
        "disclaimer": response.disclaimer,
    }
