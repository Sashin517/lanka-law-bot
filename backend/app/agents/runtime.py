"""Lazy, process-local runtime objects shared by all graph entry points."""

from __future__ import annotations

from functools import lru_cache
from typing import Any


@lru_cache(maxsize=1)
def get_graph() -> Any:
    """Build the LangGraph once, on the first request that needs it."""

    from app.agents.graph import build_graph

    return build_graph()
