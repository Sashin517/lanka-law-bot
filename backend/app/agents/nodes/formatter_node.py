"""Formatter node — builds the final API response dict from agent state.

This is the last node before END.  It converts the internal
``AgentState`` fields into the JSON structure the frontend expects,
including route metadata, markdown content, sources, grounding info,
and the execution trace for multi-agent pipeline observability.

Mode-aware output selection ensures the response matches the user's
intended mode, even when multiple agents ran in a planned pipeline.
"""

from __future__ import annotations

import logging
from typing import Optional

from langchain_core.runnables import RunnableConfig
from langsmith import traceable

from app.agents.state import AgentState
from app.agents.streaming import get_emitter

logger = logging.getLogger(__name__)

# Map user mode → expected message bus sender + msg_type
_MODE_TO_MSG: dict[str, tuple[str, str]] = {
    "quick_qa": ("quick_qa", "qa_answer"),
    "deep_research": ("deep_research", "research_findings"),
    "reasoning": ("reasoning", "reasoning_conclusion"),
    "review": ("review", "review_report"),
    "drafting": ("drafting", "draft_output"),
}


def _select_mode_output(state: AgentState) -> tuple[str, str]:
    """Select the output that matches the user's intended mode.

    For multi-step plans, the message bus contains outputs from multiple
    agents.  This function picks the output from the agent matching
    the user's mode, falling back to the last agent's state output.

    Returns
    -------
    tuple[str, str]
        ``(summary, markdown_content)`` pair for the final response.
    """
    mode = state.mode

    if mode in _MODE_TO_MSG:
        sender, msg_type = _MODE_TO_MSG[mode]
        # Search the message bus for the mode-matching agent's output
        for msg in reversed(state.agent_messages):
            if msg.sender == sender and msg.msg_type == msg_type:
                logger.info(
                    "Formatter: using output from '%s' (msg_type='%s') "
                    "matching user mode '%s'.",
                    sender,
                    msg_type,
                    mode,
                )
                # Grounding may post-process the active agent's markdown after
                # its message was emitted (for example, adding a final warning
                # after retry exhaustion). Prefer that authoritative state for
                # the last writer so formatter cannot resurrect stale output.
                if state.current_agent == sender:
                    return state.summary, state.markdown_content or msg.content
                return msg.content[:200].split("\n")[0], msg.content

    # Drafting mode fallback — use state.draft_content if message bus missed it
    if mode == "drafting" and (state.markdown_content or state.draft_content):
        return state.summary, state.markdown_content or state.draft_content

    # Fallback: use whatever is in state (last-write-wins)
    logger.info("Formatter: using default state output for mode '%s'.", mode)
    return state.summary, state.markdown_content


def _select_draft_documents(state: AgentState, markdown_content: str) -> list[dict]:
    """Return draft payloads synchronized with the final visible markdown.

    The drafting worker emits its structured payload before grounding runs.
    Grounding may subsequently revise the visible markdown, most notably by
    attaching a warning after retry exhaustion. Keep both public response
    representations aligned so downstream persistence cannot select stale,
    pre-grounding draft content.
    """
    documents = [dict(document) for document in state.draft_documents]
    if state.mode == "drafting" and documents:
        documents[0]["draft_markdown"] = markdown_content
    return documents


@traceable(name="FormatterNode")
async def formatter_node(
    state: AgentState,
    config: Optional[RunnableConfig] = None,  # noqa: UP045
) -> dict:
    """Assemble ``final_response`` from the current state."""

    emitter = get_emitter(config)
    emitter.emit_step_start("formatter", "Preparing final response")

    # ── Select the mode-appropriate output ──
    answer, markdown_content = _select_mode_output(state)
    draft_documents = _select_draft_documents(state, markdown_content)

    # Build route metadata for diagnostics
    route_dict = {
        "route": state.route,
        "task_type": state.task_type,
        "answer_mode": state.answer_mode,
        "target_corpus": state.target_corpus,
        "confidence": state.route_confidence,
        "needs_clarification": state.needs_clarification,
        "clarification_question": state.clarification_question,
    }

    # ── Execution trace (Phase 7 — frontend observability) ──
    plan = state.execution_plan
    steps_executed = min(state.current_step_index + 1, len(plan.steps))
    execution_trace = {
        "plan_type": plan.plan_type,
        "steps_executed": [
            {
                "agent": step.agent,
                "purpose": step.purpose,
            }
            for step in plan.steps[:steps_executed]
        ],
        "total_steps": len(plan.steps),
        "planning_reasoning": plan.reasoning,
        "completed_agents": list(state.completed_agents),
        "planning_seconds": state.planning_seconds,
    }

    final = {
        "route": route_dict,
        "answer": answer,
        "markdown_content": markdown_content,
        "sources": [src.model_dump() for src in state.retrieved_sources],
        "confidence": state.confidence,
        "grounding_score": state.grounding.grounding_score,
        "disclaimer": state.disclaimer,
        "draft_documents": draft_documents,
        "draft_document": draft_documents[0] if draft_documents else None,
        "draft_title": state.draft_title,
        "draft_document_type": state.draft_document_type,
        "sources_used": state.sources_used,
        "requires_completion": state.requires_completion,
        "section_map": state.section_map,
        "change_summary": state.change_summary,
        "execution_trace": execution_trace,
    }

    logger.info(
        "Response formatted: %d sources, confidence=%s, grounding=%.2f, "
        "markdown=%d chars, plan_type=%s, steps=%d.",
        len(state.retrieved_sources),
        state.confidence,
        state.grounding.grounding_score,
        len(markdown_content),
        plan.plan_type,
        steps_executed,
    )

    emitter.emit_step_done(
        "formatter",
        "Final response ready",
        source_count=len(state.retrieved_sources),
    )
    emitter.emit_final(final)

    return {"final_response": final}
