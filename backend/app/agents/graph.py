"""LangGraph orchestration graph for the LankaLawBot multi-agent system.

Topology
--------
START → router → {worker agents} → grounding → formatter → END
                  unsupported ────────────────→ formatter → END

The router uses ``Command(goto=…)`` for dynamic dispatch.
The grounding verifier uses ``Command`` for conditional retry / fallback.
All other edges are static.
"""

from __future__ import annotations

import logging

from langgraph.graph import StateGraph, START, END

from app.agents.state import AgentState
from app.agents.nodes.router_node import router_node
from app.agents.nodes.quick_qa_node import quick_qa_node
from app.agents.nodes.deep_research_node import deep_research_node
from app.agents.nodes.reasoning_node import reasoning_node
from app.agents.nodes.drafting_node import drafting_node
from app.agents.nodes.review_node import review_node
from app.agents.nodes.verify_node import verify_node
from app.agents.nodes.grounding_node import grounding_node
from app.agents.nodes.formatter_node import formatter_node
from app.agents.nodes.unsupported_node import unsupported_node

logger = logging.getLogger(__name__)

# All 6 worker nodes — each wires a static edge to grounding
_WORKER_NODES = [
    "quick_qa",
    "deep_research",
    "reasoning",
    "drafting",
    "review",
    "verify",
]


def build_graph():
    """Construct and compile the multi-agent LangGraph.

    Returns a compiled graph ready for ``graph.ainvoke(state_dict)``.
    """
    g = StateGraph(AgentState)

    # ── Register all nodes ──
    g.add_node("router", router_node)
    g.add_node("quick_qa", quick_qa_node)
    g.add_node("deep_research", deep_research_node)
    g.add_node("reasoning", reasoning_node)
    g.add_node("drafting", drafting_node)
    g.add_node("review", review_node)
    g.add_node("verify", verify_node)
    g.add_node("grounding", grounding_node)
    g.add_node("formatter", formatter_node)
    g.add_node("unsupported", unsupported_node)

    # ── Entry point ──
    g.add_edge(START, "router")
    # Router uses Command(goto=…) — no static edges needed from it.

    # ── Workers → Grounding (static edges) ──
    for worker in _WORKER_NODES:
        g.add_edge(worker, "grounding")

    # ── Unsupported skips grounding entirely ──
    g.add_edge("unsupported", "formatter")

    # ── Grounding uses Command for conditional routing ──
    # (goto="formatter" on pass, goto=current_agent on retry)

    # ── Formatter → END ──
    g.add_edge("formatter", END)

    compiled = g.compile()
    logger.info("Multi-agent graph compiled with %d nodes.", len(_WORKER_NODES) + 4)
    return compiled
