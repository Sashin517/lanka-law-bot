import logging
from fastapi import APIRouter

from app.schemas.requests import LegalQuery
from app.agent import process_query_with_route

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/")
def read_root():
    """Health check endpoint."""
    return {"status": "LankaLawBot Backend is running!"}


@router.post("/search")
async def search_law(query: LegalQuery):
    logger.info("Received query: '%s'", query.question[:100])

    response, route = await process_query_with_route(query.question)

    # Build the "results" array the frontend expects
    results = []
    for i, source in enumerate(response.sources):
        results.append({
            "id": source.citation_id or f"source-{i}",
            "title": source.title or "Unknown Act",
            "subtitle": f"Year: {source.year} | {source.section or 'N/A'}",
            "excerpt": source.excerpt or "",
            "score": response.confidence or "medium",
        })

    return {
        "route": route.model_dump(),
        "answer": response.summary,
        "results": results,  # <-- the key the frontend reads
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
