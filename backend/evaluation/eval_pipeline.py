"""Shared evaluation pipeline — runs queries through LangGraph (production path).

All evaluation scripts (run_evaluation, ragas_eval, ablation_runner) import from
this module to ensure they exercise the same code path as ``POST /api/search``.

This replaces the old ``app.agent.process_query_with_route()`` orchestrator
which depended on the deleted ``intent_routing`` package.
"""

from __future__ import annotations

import logging

from app.agents.graph import build_graph
from app.agents.state import AgentState

logger = logging.getLogger(__name__)

_graph = None


def get_graph():
    """Lazy-init the compiled LangGraph (expensive first call)."""
    global _graph
    if _graph is None:
        logger.info("Compiling LangGraph for evaluation …")
        _graph = build_graph()
    return _graph


async def run_pipeline(
    question: str,
    mode: str = "quick_qa",
    document_ids: list[str] | None = None,
    matter_id: str | None = None,
    ablation_config: dict | None = None,
) -> dict:
    """Run a single query through the compiled LangGraph.

    This is the single source of truth for evaluation — the same path
    that ``POST /api/search`` uses in production.

    Parameters
    ----------
    question : str
        The user's legal question.
    mode : str
        One of ``quick_qa``, ``deep_research``, ``drafting``,
        ``review``, ``reasoning``.
    document_ids : list[str] | None
        Attached user-document IDs, if any.
    matter_id : str | None
        Grouping key for user documents.
    ablation_config : dict | None
        Overrides for ablation studies.

    Returns
    -------
    dict
        The full ``AgentState`` dict after graph execution.
        Contains ``final_response``, ``summary``, ``route``,
        ``retrieved_sources``, ``analysis``, etc.
    """
    graph = get_graph()

    initial_state = AgentState(
        question=question,
        mode=mode,
        document_ids=document_ids or [],
        matter_id=matter_id,
        ablation_config=ablation_config or {},
    )

    final_state = await graph.ainvoke(initial_state.model_dump())
    return final_state
