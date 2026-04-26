from fastapi import APIRouter
from app.api.endpoints import query_routes

api_router = APIRouter()
api_router.include_router(query_routes.router, prefix="/api", tags=["search"])
