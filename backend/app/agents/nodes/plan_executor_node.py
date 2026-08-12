"""Plan Executor node — steps through the supervisor's execution plan.

After each agent completes and passes grounding, this node checks
whether there are more steps remaining in the ``ExecutionPlan``.

Routing logic (via ``Command``):
- More steps remain  → advance ``current_step_index``, dispatch to
  the next agent via ``Command(goto=next_agent)``
- Plan complete       → route to ``formatter``

This node is the core of the multi-agent chaining loop:

  supervisor → agent[0] → grounding ✓ → plan_executor
             → agent[1] → grounding ✓ → plan_executor
             → agent[n] → grounding ✓ → plan_executor → formatter → END
"""

from __future__ import annotations

import logging
from typing import Literal, Optional

from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from langsmith import traceable

from app.agents.state import AgentState
from app.agents.streaming import get_emitter

logger = logging.getLogger(__name__)


@traceable(name="PlanExecutor")
async def plan_executor_node(
    state: AgentState,
    config: Optional[RunnableConfig] = None,  # noqa: UP045
) -> Command[
    Literal[
        "quick_qa",
        "deep_research",
        "reasoning",
        "drafting",
        "review",
        "verify",
        "formatter",
    ]
]:
    """Advance to the next step in the execution plan, or finish.

    Reads ``current_step_index`` from state, increments it, and
    dispatches to the next agent.  If all steps are done, routes
    to the formatter for final response assembly.
    """

    emitter = get_emitter(config)
    emitter.emit_step_start("plan_executor", "Advancing execution plan")

    plan = state.execution_plan
    next_index = state.current_step_index + 1

    # ── Plan complete — route to formatter ──
    if next_index >= len(plan.steps):
        logger.info(
            "Plan complete after %d steps. Routing to formatter.",
            len(plan.steps),
        )
        emitter.emit_step_done(
            "plan_executor",
            "All planned steps completed",
            completed_steps=len(plan.steps),
            next_node="formatter",
        )
        return Command(
            update={"current_step_index": next_index},
            goto="formatter",
        )

    # ── Advance to the next agent in the plan ──
    next_step = plan.steps[next_index]

    logger.info(
        "Plan step %d/%d: dispatching to '%s' (purpose: %s).",
        next_index + 1,
        len(plan.steps),
        next_step.agent,
        next_step.purpose,
    )
    emitter.emit_step_detail(
        "plan_executor",
        f"Advancing to next step: {next_step.agent.replace('_', ' ').title()}",
        step_index=next_index,
        total_steps=len(plan.steps),
    )

    # Build state updates — include config overrides from the plan step
    updates: dict = {
        "current_step_index": next_index,
        "current_agent": next_step.agent,
        # Reset retry count for the new agent
        "retry_count": 0,
    }

    # Apply any config overrides specified by the planner
    # (e.g., {"legal_top_k": 12} for broader retrieval)
    if next_step.config_overrides:
        updates.update(next_step.config_overrides)

    emitter.emit_step_done(
        "plan_executor",
        f"Next agent: {next_step.agent.replace('_', ' ').title()}",
        next_agent=next_step.agent,
        step_index=next_index,
        total_steps=len(plan.steps),
    )

    return Command(update=updates, goto=next_step.agent)
