from fastapi import APIRouter

from app.api.endpoints import (
    conversation_routes,
    document_routes,
    draft_routes,
    prompt_routes,
    query_routes,
)

api_router = APIRouter()
api_router.include_router(query_routes.router, prefix="/api", tags=["search"])
api_router.include_router(prompt_routes.router, prefix="/api/prompt", tags=["prompt"])
api_router.include_router(
    document_routes.router, prefix="/api/documents", tags=["documents"]
)
api_router.include_router(draft_routes.router, prefix="/api/drafts", tags=["drafts"])
api_router.include_router(
    draft_routes.edit_router,
    prefix="/api/draft",
    tags=["drafting"],
)
api_router.include_router(
    conversation_routes.router,
    prefix="/api/conversations",
    tags=["conversations"],
)
