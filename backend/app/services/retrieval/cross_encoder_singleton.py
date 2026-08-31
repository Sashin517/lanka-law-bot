from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_shared_cross_encoder() -> Any:
    """Instantiate and cache the shared HuggingFaceCrossEncoder model.

    This ensures that both Legal Retrieval and User Document Retrieval
    share the exact same underlying model weights and tokenizer in memory,
    avoiding redundant remote network checks and duplicate memory allocation.
    """
    logger.info(
        "Initializing shared HuggingFaceCrossEncoder singleton (model=%s)...",
        settings.RERANKER_MODEL,
    )
    from langchain_community.cross_encoders import HuggingFaceCrossEncoder

    return HuggingFaceCrossEncoder(model_name=settings.RERANKER_MODEL)
