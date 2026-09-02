from __future__ import annotations

import logging
from threading import Lock
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


_cross_encoder: Any | None = None
_cross_encoder_lock = Lock()


def get_shared_cross_encoder() -> Any:
    """Instantiate and cache the shared HuggingFaceCrossEncoder model.

    This ensures that both Legal Retrieval and User Document Retrieval
    share the exact same underlying model weights and tokenizer in memory,
    avoiding redundant remote network checks and duplicate memory allocation.
    """
    global _cross_encoder
    if _cross_encoder is None:
        with _cross_encoder_lock:
            if _cross_encoder is None:
                logger.info(
                    "Initializing shared HuggingFaceCrossEncoder singleton "
                    "(model=%s)...",
                    settings.RERANKER_MODEL,
                )
                from langchain_community.cross_encoders import HuggingFaceCrossEncoder

                _cross_encoder = HuggingFaceCrossEncoder(
                    model_name=settings.RERANKER_MODEL
                )
    return _cross_encoder
