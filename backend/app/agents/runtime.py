"""Lazy, process-local runtime objects shared by all graph entry points."""

from __future__ import annotations

from threading import Lock
from typing import Any

_graph: Any | None = None
_graph_lock = Lock()


def get_graph() -> Any:
    """Build the LangGraph once, on the first request that needs it."""

    global _graph
    if _graph is None:
        with _graph_lock:
            if _graph is None:
                from app.agents.graph import build_graph

                _graph = build_graph()
    return _graph
