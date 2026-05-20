from fastapi import APIRouter
from app.api.endpoints import document_routes, query_routes

api_router = APIRouter()
api_router.include_router(query_routes.router, prefix="/api", tags=["search"])
api_router.include_router(document_routes.router, prefix="/api/documents", tags=["documents"])
