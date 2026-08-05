"""LangGraph orchestration graph for the LankaLawBot multi-agent system.

Topology
--------
START → supervisor → {worker agents} → grounding → plan_executor → ...
                                                  → formatter → END

Fast-path (quick_qa, simple drafting):
  supervisor → agent → grounding ✓ → formatter → END

Planned multi-step (complex drafting, research+reasoning):
  supervisor → agent[0] → grounding ✓ → plan_executor
             → agent[1] → grounding ✓ → plan_executor
             → agent[n] → grounding ✓ → formatter → END

The supervisor uses ``Command(goto=…)`` for dynamic dispatch.
For complex queries, the supervisor generates an ExecutionPlan
with multiple steps (inter-agent communication via message bus).
The grounding verifier uses ``Command`` for plan-aware conditional routing.
The plan executor uses ``Command`` to advance through the plan.
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
from app.agents.nodes.plan_executor_node import plan_executor_node
from app.agents.nodes.formatter_node import formatter_node

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
    g.add_node("supervisor", router_node)
    g.add_node("quick_qa", quick_qa_node)
    g.add_node("deep_research", deep_research_node)
    g.add_node("reasoning", reasoning_node)
    g.add_node("drafting", drafting_node)
    g.add_node("review", review_node)
    g.add_node("verify", verify_node)
    g.add_node("grounding", grounding_node)
    g.add_node("plan_executor", plan_executor_node)
    g.add_node("formatter", formatter_node)

    # ── Entry point ──
    g.add_edge(START, "supervisor")
    # Supervisor uses Command(goto=…) — no static edges needed from it.

    # ── Workers → Grounding (static edges) ──
    # Every worker agent output must pass through the grounding verifier.
    for worker in _WORKER_NODES:
        g.add_edge(worker, "grounding")

    # ── Grounding uses Command for plan-aware conditional routing ──
    # - Grounded + more plan steps  → plan_executor
    # - Grounded + plan complete    → formatter
    # - Not grounded + retries left → current_agent (retry)
    # - Max retries exhausted       → formatter (fallback)

    # ── Plan Executor uses Command for dynamic dispatch ──
    # - More steps remain → next agent in plan
    # - Plan complete     → formatter

    # ── Formatter → END ──
    g.add_edge("formatter", END)

    compiled = g.compile()
    logger.info(
        "Multi-agent graph compiled: %d workers + supervisor + grounding + plan_executor + formatter = %d nodes.",
        len(_WORKER_NODES),
        len(_WORKER_NODES) + 4,
    )
    return compiled
