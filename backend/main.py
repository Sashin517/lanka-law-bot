from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from dotenv import load_dotenv

# Load environment variables before any other imports so LangSmith picks them up
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.api_routes import api_router
from app.auth.firebase_auth import init_firebase_admin
from app.core.config import settings
from app.database.postgres_session import (
    check_postgres_connection,
    close_postgres,
    init_postgres,
)
from app.database.session import init_db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-30s | %(levelname)-7s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Initialize local metadata and optional chat infrastructure safely."""
    init_db()
    if settings.POSTGRES_AUTO_CREATE_SCHEMA:
        await init_postgres()
    else:
        await check_postgres_connection()
    init_firebase_admin()
    try:
        yield
    finally:
        await close_postgres()


# FastAPI App
app = FastAPI(
    title="LankaLawBot API",
    description="AI-powered Sri Lankan legal research assistant",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


app.include_router(api_router)
