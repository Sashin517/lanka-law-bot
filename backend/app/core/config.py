from __future__ import annotations

import os
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

class Settings(BaseSettings):
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    BASE_DIR: str = _BACKEND_DIR
    DATA_PATH: str = os.path.join(_BACKEND_DIR, "data")
    
    # --- CHROMA DB PATHS RESTORED ---
    CHROMA_PATH: str = os.path.join(_BACKEND_DIR, "database", "chroma_db")
    USER_CHROMA_PATH: str = os.path.join(_BACKEND_DIR, "database", "user_chroma_db")

    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"

    USER_UPLOAD_DIR: str = os.path.join(_BACKEND_DIR, "storage", "uploads")
    USER_MARKDOWN_DIR: str = os.path.join(_BACKEND_DIR, "storage", "processed_markdown")
    METADATA_DB_PATH: str = os.path.join(_BACKEND_DIR, "database", "metadata.sqlite3")

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

    RETRIEVAL_CANDIDATES_K: int = 30
    DENSE_WEIGHT: float = 0.6
    SPARSE_WEIGHT: float = 0.4

    RERANKER_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    RERANKER_TOP_N: int = 15
    USER_DOC_RERANKER_TOP_N: int = 12
    RELEVANCE_SCORE_THRESHOLD: float = 0.0

    # GOOGLE_API_KEY: str = ""
    # LLM_MODEL_NAME: str = "gemini-3.1-flash-lite-preview"
    # LLM_TEMPERATURE: float = 0.1
    # PROMPT_IMPROVE_TEMPERATURE: float = 0.35
    # LLM_MAX_TOKENS: int = 2048

    OPENROUTER_API_KEY: str
    LLM_MODEL_NAME: str = "openai/gpt-oss-120b:free"
    LLM_TEMPERATURE: float = 0.1                 # Keeps the legal analysis strict and factual
    PROMPT_IMPROVE_TEMPERATURE: float = 0.35     # Slightly more creative for suggesting prompt improvements
    LLM_MAX_TOKENS: int = 2048                   # Ensures the model doesn't get cut off mid-sentence

    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USERNAME: str = "neo4j"
    NEO4J_PASSWORD: str = "password"

    model_config = SettingsConfigDict(
        env_file=os.path.join(_BACKEND_DIR, ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

settings = Settings()


from langchain_openai import ChatOpenAI

LLM_FALLBACK_MODELS: list[str] = [
    # Tier 1 — Best for legal JSON + agentic chains
    "openai/gpt-oss-120b:free",               # Best instruction following, JSON, already proven

    # Tier 2 — Best for long context RAG (1M tokens, 4 providers = high uptime)
    "nvidia/nemotron-3-super-120b-a12b:free",  # 1M context, 2.2x faster, best for deep_research

    # Tier 3 — Best large Qwen model (480B, 1M context, strong agentic)
    "qwen/qwen3-coder-480b-a35b:free",         # Massive model, strong tool use + JSON

    # Tier 4 — Lighter Qwen for quick_qa speed
    "qwen/qwen3-next-80b-a3b-instruct:free",   # Faster, good for simple QA nodes

    # Tier 5 — Reliable general fallback
    "meta-llama/llama-3.3-70b-instruct:free",  # Battle-tested, widely available

    # Last resort — OpenRouter picks any available free model
    "openrouter/free",
]

_OPENROUTER_HEADERS = {
    "extra_headers": {
        "HTTP-Referer": "https://lankalawbot.com",
        "X-Title": "LankaLawBot",
    }
}

def make_llm(temperature: float | None = None, max_tokens: int | None = None) -> ChatOpenAI:
    """Create a ChatOpenAI instance pointing at OpenRouter."""
    return ChatOpenAI(
        model_name=settings.LLM_MODEL_NAME,
        openai_api_key=settings.OPENROUTER_API_KEY,
        openai_api_base="https://openrouter.ai/api/v1",
        temperature=temperature if temperature is not None else settings.LLM_TEMPERATURE,
        max_tokens=max_tokens or settings.LLM_MAX_TOKENS,
        model_kwargs=_OPENROUTER_HEADERS,
    )

async def invoke_with_fallback(chain_builder, inputs: dict, temperature: float | None = None) -> dict:
    """Try each fallback model until one succeeds.
    
    chain_builder: callable(llm) -> runnable chain
    inputs: dict passed to chain.ainvoke()
    """
    import logging
    logger = logging.getLogger(__name__)
    
    last_error = None
    for model_id in LLM_FALLBACK_MODELS:
        try:
            llm = ChatOpenAI(
                model_name=model_id,
                openai_api_key=settings.OPENROUTER_API_KEY,
                openai_api_base="https://openrouter.ai/api/v1",
                temperature=temperature if temperature is not None else settings.LLM_TEMPERATURE,
                max_tokens=settings.LLM_MAX_TOKENS,
                model_kwargs=_OPENROUTER_HEADERS,
            )
            chain = chain_builder(llm)
            result = await chain.ainvoke(inputs)
            logger.info("invoke_with_fallback succeeded with model: %s", model_id)
            return result
        except Exception as e:
            logger.warning("Model %s failed: %s — trying next.", model_id, e)
            last_error = e
    
    raise RuntimeError(f"All fallback models failed. Last error: {last_error}")