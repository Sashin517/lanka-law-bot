"""Deterministic token accounting for persisted conversation memory."""

from __future__ import annotations

import logging
from functools import lru_cache

import tiktoken
from tiktoken import Encoding

_ENCODING_NAME = "cl100k_base"
logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _encoding() -> Encoding | None:
    """Load the tokenizer once and fail safely in offline deployments."""
    try:
        return tiktoken.get_encoding(_ENCODING_NAME)
    except Exception:
        logger.warning(
            "Unable to load %s tokenizer; using deterministic fallback counts.",
            _ENCODING_NAME,
            exc_info=True,
        )
        return None


def count_tokens(text: str) -> int:
    """Return the exact ``cl100k_base`` token count for ``text``."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if not text:
        return 0
    encoding = _encoding()
    if encoding is None:
        return max(1, (len(text) + 3) // 4)
    return len(encoding.encode(text, disallowed_special=()))


def truncate_to_token_budget(text: str, max_tokens: int) -> str:
    """Return a readable prefix whose encoded length does not exceed a budget."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if isinstance(max_tokens, bool) or not isinstance(max_tokens, int):
        raise TypeError("max_tokens must be an integer")
    if max_tokens <= 0 or not text:
        return ""

    encoding = _encoding()
    if encoding is None:
        if count_tokens(text) <= max_tokens:
            return text
        max_chars = max_tokens * 4
        return f"{text[: max(0, max_chars - 1)].rstrip()}…"[:max_chars]
    tokens = encoding.encode(text, disallowed_special=())
    if len(tokens) <= max_tokens:
        return text

    ellipsis = "…"
    ellipsis_tokens = encoding.encode(ellipsis, disallowed_special=())
    content_budget = max(0, max_tokens - len(ellipsis_tokens))
    truncated = encoding.decode(tokens[:content_budget]).rstrip()
    result = f"{truncated}{ellipsis}" if truncated else ellipsis
    while result and count_tokens(result) > max_tokens:
        result = result[:-1]
    return result


def truncate_middle_to_token_budget(
    text: str,
    max_tokens: int,
    *,
    separator: str = "\n[… earlier/middle details compressed …]\n",
) -> str:
    """Bound long cumulative summaries while retaining old and recent details."""
    if count_tokens(text) <= max_tokens:
        return text
    if max_tokens <= 0:
        return ""

    encoding = _encoding()
    if encoding is None:
        if max_tokens <= 0:
            return ""
        max_chars = max_tokens * 4
        if len(text) <= max_chars:
            return text
        separator_chars = separator[: max_chars // 3]
        available = max(0, max_chars - len(separator_chars))
        head_size = available // 2
        tail_size = available - head_size
        return (
            f"{text[:head_size].rstrip()}{separator_chars}{text[-tail_size:].lstrip()}"
        )[:max_chars]
    source_tokens = encoding.encode(text, disallowed_special=())
    separator_tokens = encoding.encode(separator, disallowed_special=())
    if len(separator_tokens) >= max_tokens:
        return truncate_to_token_budget(separator, max_tokens)

    available = max_tokens - len(separator_tokens)
    head_size = available // 2
    tail_size = available - head_size
    result = (
        f"{encoding.decode(source_tokens[:head_size]).rstrip()}"
        f"{separator}"
        f"{encoding.decode(source_tokens[-tail_size:]).lstrip()}"
    )
    return truncate_to_token_budget(result, max_tokens)
