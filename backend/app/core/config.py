from __future__ import annotations

import os
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


# Resolve paths relative to the *backend* directory
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class Settings(BaseSettings):

    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    BASE_DIR: str = _BACKEND_DIR
    CHROMA_PATH: str = os.path.join(_BACKEND_DIR, "database", "chroma_db")
    DATA_PATH: str = os.path.join(_BACKEND_DIR, "data")

    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"


    PARENT_CHUNK_SIZE: int = 2000
    PARENT_CHUNK_OVERLAP: int = 200
    CHILD_CHUNK_SIZE: int = 500
    CHILD_CHUNK_OVERLAP: int = 100

    RETRIEVAL_CANDIDATES_K: int = 15  
    DENSE_WEIGHT: float = 0.6
    SPARSE_WEIGHT: float = 0.4

    RERANKER_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    RERANKER_TOP_N: int = 5

    GOOGLE_API_KEY: str = ""
    LLM_MODEL_NAME: str = "gemini-3.1-flash-lite-preview"
    LLM_TEMPERATURE: float = 0.1
    LLM_MAX_TOKENS: int = 2048

    model_config = SettingsConfigDict(
        env_file=os.path.join(_BACKEND_DIR, ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
