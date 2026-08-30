from __future__ import annotations

import os

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

# Resolve paths relative to the *backend* directory
_BACKEND_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)


class Settings(BaseSettings):
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://10.148.67.159:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    BASE_DIR: str = _BACKEND_DIR
    DATA_PATH: str = os.path.join(_BACKEND_DIR, "data")

    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"

    USER_UPLOAD_DIR: str = os.path.join(_BACKEND_DIR, "storage", "uploads")
    USER_MARKDOWN_DIR: str = os.path.join(_BACKEND_DIR, "storage", "processed_markdown")
    PINECONE_API_KEY: str = ""
    PINECONE_INDEX_HOST: str = ""
    PINECONE_INDEX_NAME: str = "lawdex-index"
    PINECONE_NAMESPACE: str = "user_documents"

    PINECONE_LEGAL_INDEX_HOST: str = ""
    PINECONE_LEGAL_INDEX_NAME: str = "lawdex-legal-index"
    PINECONE_LEGAL_NAMESPACE: str = "legal_corpus"

    PINECONE_LEGAL_BM25_INDEX_HOST: str = ""
    PINECONE_LEGAL_BM25_INDEX_NAME: str = "lawdex-legal-bm25-index"
    PINECONE_LEGAL_BM25_NAMESPACE: str = "legal_corpus"

    PINECONE_LEGAL_DENSE_FIELD: str = "dense_vector"
    PINECONE_LEGAL_BODY_FIELD: str = "text"

    PINECONE_EMBEDDING_MODEL: str = "jina-embeddings-v4"
    PINECONE_EMBEDDING_DIMENSION: int = 2048

    UPLOAD_MAX_MB: int = 50
    ALLOWED_UPLOAD_EXTENSIONS: list[str] = [".pdf", ".docx", ".txt", ".md"]
    # Docling PDF parsing: keep only what legal chunking needs (text + optional OCR).
    DOCLING_DEVICE: str = "auto"  # auto | cpu | cuda | cuda:0 | mps
    DOCLING_NUM_THREADS: int = 1
    DOCLING_ENABLE_OCR: bool = True
    DOCLING_ENABLE_TABLE_STRUCTURE: bool = False
    DOCLING_PREFER_NATIVE_PDF_TEXT: bool = True
    DOCLING_NATIVE_TEXT_MIN_CHARS: int = 200
    INGESTION_BATCH_SIZE: int = 32
    PINECONE_UPSERT_TIMEOUT: float = 60.0
    USER_PARENT_CHUNK_SIZE: int = 2200
    USER_PARENT_CHUNK_OVERLAP: int = 250
    USER_CHILD_CHUNK_SIZE: int = 550
    USER_CHILD_CHUNK_OVERLAP: int = 120

    PARENT_CHUNK_SIZE: int = 2000
    PARENT_CHUNK_OVERLAP: int = 200
    CHILD_CHUNK_SIZE: int = 500
    CHILD_CHUNK_OVERLAP: int = 100

    RETRIEVAL_CANDIDATES_K: int = 30
    DENSE_WEIGHT: float = 0.6
    SPARSE_WEIGHT: float = 0.4

    RERANKER_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    RERANKER_TOP_N: int = 15
    USER_DOC_RERANKER_TOP_N: int = 12
    RELEVANCE_SCORE_THRESHOLD: float = 0.0

    GOOGLE_API_KEY: str = ""
    JINA_API_KEY: str = ""
    JINA_EMBEDDING_MODEL: str = "jina-embeddings-v4"
    JINA_EMBEDDING_DIMENSION: int = 2048
    LLM_MODEL_NAME: str = "gemini-3.1-flash-lite"
    LLM_TEMPERATURE: float = 0.1
    PROMPT_IMPROVE_TEMPERATURE: float = 0.35
    LLM_MAX_TOKENS: int = 2048

    # === Neo4j Settings ===
    RETRIEVAL_BACKEND: str = "pinecone"  # "pinecone" | "neo4j" | "both"
    NEO4J_URI: str = "neo4j+s://928438a5.databases.neo4j.io"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = ""
    NEO4J_DATABASE: str = "neo4j"
    NEO4J_INDEX_MIGRATION_MODE: str = "validate"
    NEO4J_BACKUP_CONFIRMED: bool = False
    NEO4J_BACKUP_REFERENCE: str = ""

    NEO4J_EMBEDDING_MODEL: str = "jina-embeddings-v4"
    NEO4J_EMBEDDING_DIMENSION: int = 2048
    NEO4J_VECTOR_INDEX_NAME: str = "chunk-embeddings"
    NEO4J_FULLTEXT_INDEX_NAME: str = "chunk-fulltext"
    NEO4J_WORK_FULLTEXT_INDEX_NAME: str = "legal-work-fulltext"

    NEO4J_VECTOR_CANDIDATES_K: int = 30
    NEO4J_FTS_CANDIDATES_K: int = 30
    NEO4J_AUTHORITY_CANDIDATES_K: int = 20
    NEO4J_GRAPH_TRAVERSAL_LIMIT: int = 15
    NEO4J_FILTER_OVERFETCH_FACTOR: int = 4
    NEO4J_VECTOR_WEIGHT: float = 0.4
    NEO4J_FTS_WEIGHT: float = 0.3
    NEO4J_GRAPH_WEIGHT: float = 0.3
    NEO4J_AUTHORITY_WEIGHT: float = 0.8
    NEO4J_BATCH_SIZE: int = 100

    # PostgreSQL is the single relational persistence layer for conversations,
    # uploaded-document metadata, ingestion jobs, and drafting/version data.
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = Field(default=5432, ge=1, le=65535)
    POSTGRES_USER: str = "lankalawbot"
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str = "lankalawbot"
    POSTGRES_POOL_SIZE: int = Field(default=10, ge=1)
    POSTGRES_MAX_OVERFLOW: int = Field(default=5, ge=0)
    POSTGRES_AUTO_CREATE_SCHEMA: bool = False

    # Firebase Admin uses this file when supplied and otherwise relies on
    # Application Default Credentials.
    FIREBASE_SERVICE_ACCOUNT_PATH: str = ""
    FIREBASE_PROJECT_ID: str = ""
    FIREBASE_CHECK_REVOKED_TOKENS: bool = False
    FIREBASE_CLOCK_SKEW_SECONDS: int = Field(default=0, ge=0, le=60)

    # Conversation-memory defaults used by later service-layer phases.
    CONTEXT_WINDOW_MAX_TOKENS: int = Field(default=4096, ge=1)
    SUMMARY_MAX_TOKENS: int = Field(default=800, ge=1)
    SUMMARY_TRIGGER_MESSAGE_COUNT: int = Field(default=20, ge=1)
    SLIDING_WINDOW_SIZE: int = Field(default=10, ge=1)
    AUTO_TITLE_AFTER_MESSAGES: int = Field(default=2, ge=1)

    @property
    def postgres_url(self) -> URL:
        """Return a structured URL without hand-assembling credentials."""
        return URL.create(
            drivername="postgresql+asyncpg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_HOST,
            port=self.POSTGRES_PORT,
            database=self.POSTGRES_DB,
        )

    @property
    def postgres_dsn(self) -> str:
        """Return the async PostgreSQL DSN with safely escaped credentials."""
        return self.postgres_url.render_as_string(hide_password=False)

    @property
    def postgres_sync_url(self) -> URL:
        """Return the PostgreSQL URL used by existing synchronous services."""
        return self.postgres_url.set(drivername="postgresql+psycopg")

    @property
    def postgres_sync_dsn(self) -> str:
        """Return the synchronous PostgreSQL DSN with escaped credentials."""
        return self.postgres_sync_url.render_as_string(hide_password=False)

    model_config = SettingsConfigDict(
        env_file=os.path.join(_BACKEND_DIR, ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
