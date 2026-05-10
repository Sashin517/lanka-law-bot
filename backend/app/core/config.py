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

    USER_UPLOAD_DIR: str = os.path.join(_BACKEND_DIR, "storage", "uploads")
    USER_MARKDOWN_DIR: str = os.path.join(_BACKEND_DIR, "storage", "processed_markdown")
    METADATA_DB_PATH: str = os.path.join(_BACKEND_DIR, "database", "metadata.sqlite3")

    QDRANT_URL: str = ""
    QDRANT_API_KEY: str = ""
    QDRANT_COLLECTION_USER_DOCS: str = "user_documents"

    VOYAGE_API_KEY: str = ""
    VOYAGE_EMBEDDING_MODEL: str = "voyage-law-2"
    VOYAGE_EMBEDDING_DIMENSION: int = 1024
    VOYAGE_EMBEDDING_INPUT_TYPE: str = "document"

    UPLOAD_MAX_MB: int = 50
    ALLOWED_UPLOAD_EXTENSIONS: List[str] = [".pdf", ".docx", ".txt", ".md"]
    INGESTION_BATCH_SIZE: int = 64
    USER_PARENT_CHUNK_SIZE: int = 2200
    USER_PARENT_CHUNK_OVERLAP: int = 250
    USER_CHILD_CHUNK_SIZE: int = 550
    USER_CHILD_CHUNK_OVERLAP: int = 120


    PARENT_CHUNK_SIZE: int = 2000
    PARENT_CHUNK_OVERLAP: int = 200
    CHILD_CHUNK_SIZE: int = 500
    CHILD_CHUNK_OVERLAP: int = 100

    RETRIEVAL_CANDIDATES_K: int = 15  
    DENSE_WEIGHT: float = 0.6
    SPARSE_WEIGHT: float = 0.4

    RERANKER_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    RERANKER_TOP_N: int = 5
    USER_DOC_RERANKER_TOP_N: int = 8

    GOOGLE_API_KEY: str = ""
    LLM_MODEL_NAME: str = "gemini-3.1-flash-lite-preview"
    LLM_TEMPERATURE: float = 0.1
    LLM_MAX_TOKENS: int = 2048

    ROUTER_MODEL_NAME: str = ""
    ROUTER_TEMPERATURE: float = 0.0
    ROUTER_MAX_TOKENS: int = 1024
    ROUTER_ENABLE_LLM: bool = True

    model_config = SettingsConfigDict(
        env_file=os.path.join(_BACKEND_DIR, ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
