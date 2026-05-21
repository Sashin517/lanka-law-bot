"""LankaLawBot multi-agent system powered by LangGraph.

The graph imports retrieval and LLM clients, so expose it lazily to avoid
startup-time model initialization when only lightweight agent modules are used.
"""

from __future__ import annotations

from typing import Any

__all__ = ["build_graph"]


def __getattr__(name: str) -> Any:
    if name != "build_graph":
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from app.agents.graph import build_graph

    globals()[name] = build_graph
    return build_graph
