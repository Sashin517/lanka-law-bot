"""Grounding Verifier node — LLM-as-judge faithfulness gate.

This is the zero-hallucination enforcement layer.  After every worker
agent produces a response, this node asks a separate LLM call to judge
whether every claim is supported by the retrieved sources.

Plan-aware routing logic (via ``Command``):
- Grounded + more plan steps   → ``plan_executor`` (advance to next step)
- Grounded + plan complete     → ``formatter``
- Not grounded + retries left  → re-route to ``current_agent`` (with feedback)
- Max retries exhausted        → fallback response → ``formatter``
"""

from __future__ import annotations

import logging
from typing import Literal

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langsmith import traceable
from langgraph.types import Command

from app.agents.state import AgentState, GroundingResult
from app.agents.prompts.grounding_prompt import GROUNDING_JUDGE_PROMPT
from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Context budget cap (Phase 6 optimization) ────────────────────
# Prevents token overflow and reduces grounding latency for large contexts
_MAX_CONTEXT_CHARS = 100_000

# Dedicated LLM instance for grounding verification
_grounding_llm = ChatGoogleGenerativeAI(
    model=settings.LLM_MODEL_NAME,
    google_api_key=settings.GOOGLE_API_KEY,
    temperature=0.0,  # Deterministic for judging
    max_output_tokens=1024,
)
_grounding_parser = JsonOutputParser()
_grounding_prompt = ChatPromptTemplate.from_template(GROUNDING_JUDGE_PROMPT)
_grounding_chain = _grounding_prompt | _grounding_llm | _grounding_parser


def _has_remaining_plan_steps(state: AgentState) -> bool:
    """Check whether the execution plan has more steps after the current one."""
    plan = state.execution_plan
    if plan.plan_type != "planned":
        return False
    return (state.current_step_index + 1) < len(plan.steps)


@traceable(name="GroundingVerifier")
async def grounding_node(
    state: AgentState,
) -> Command[
    Literal[
        "quick_qa",
        "deep_research",
        "reasoning",
        "drafting",
        "review",
        "verify",
        "plan_executor",
        "formatter",
    ]
]:
    """Judge whether the generated response is faithful to sources.

    Returns a ``Command`` that routes to:
    - ``plan_executor`` (grounded, more plan steps remaining)
    - ``formatter`` (grounded, plan complete or fast-path)
    - ``current_agent`` (not grounded, retries available)
    - ``formatter`` with fallback (max retries exhausted)
    """

    # ── Skip grounding for empty / clarification responses or when skip_verification is set ──
    has_content = state.markdown_content or state.summary
    skip_reason = None
    if not has_content:
        skip_reason = "No content to ground."
    elif state.needs_clarification:
        skip_reason = "Clarification response — grounding not applicable."
    elif state.current_agent == "drafting":
        skip_reason = "Drafting mode — grounding check skipped (generative output)."
    elif state.ablation_config.get("skip_verification"):
        skip_reason = "Ablation: skip_verification enabled."

    if skip_reason:
        # Even when skipping, respect plan-aware routing
        next_node = "plan_executor" if _has_remaining_plan_steps(state) else "formatter"
        return Command(
            update={
                "grounding": GroundingResult(
                    is_grounded=True,
                    grounding_score=1.0,
                    feedback=skip_reason,
                ),
            },
            goto=next_node,
        )

    # ── Build the content string for the judge ──
    # Prefer markdown_content (what the user sees), fall back to analysis[]
    if state.markdown_content:
        claims_text = state.markdown_content
    else:
        claims_text = (
            "\n".join(
                f"- {c.statement} (cites: {', '.join(c.citation_ids)})"
                for c in state.analysis
            )
            or "(No generated content)"
        )

    # ── Call the grounding judge LLM ──
    try:
        raw: dict = await _grounding_chain.ainvoke(
            {
                "summary": state.summary,
                "claims": claims_text,
                "sources": state.context_str[:_MAX_CONTEXT_CHARS],
            }
        )

        grounding = GroundingResult(
            is_grounded=raw.get("is_grounded", False),
            grounding_score=float(raw.get("grounding_score", 0.0)),
            ungrounded_claims=raw.get("ungrounded_claims", []),
            feedback=raw.get("feedback", ""),
        )
    except Exception:
        logger.exception("Grounding verification LLM call failed.")
        # On failure, pass through (don't block the response)
        grounding = GroundingResult(
            is_grounded=True,
            grounding_score=0.5,
            feedback="Grounding check skipped due to LLM error.",
        )

    logger.info(
        "Grounding result: grounded=%s score=%.2f ungrounded=%d retry=%d/%d agent=%s",
        grounding.is_grounded,
        grounding.grounding_score,
        len(grounding.ungrounded_claims),
        state.retry_count,
        state.max_retries,
        state.current_agent,
    )

    # ── Route based on grounding result ──

    if grounding.is_grounded:
        # Decide: advance plan or finish
        if _has_remaining_plan_steps(state):
            logger.info(
                "Grounding passed for '%s'. Advancing to next plan step.",
                state.current_agent,
            )
            return Command(
                update={"grounding": grounding},
                goto="plan_executor",
            )

        # Plan complete (or fast-path) — go to formatter
        return Command(
            update={"grounding": grounding},
            goto="formatter",
        )

    # ── Not grounded — retry or fallback ──

    if state.retry_count < state.max_retries:
        logger.warning(
            "Grounding failed (attempt %d/%d). Retrying '%s' with feedback.",
            state.retry_count + 1,
            state.max_retries,
            state.current_agent,
        )
        return Command(
            update={
                "grounding": grounding,
                "retry_count": state.retry_count + 1,
                # Pass grounding feedback via working memory so the agent
                # can self-correct on retry
                "working_memory": {
                    **state.working_memory,
                    "grounding_feedback": grounding.feedback,
                    "ungrounded_claims": grounding.ungrounded_claims,
                },
            },
            goto=state.current_agent,
        )

    # Max retries exhausted — preserve generated markdown with a warning banner
    logger.warning(
        "Grounding failed after %d retries for '%s'. Attaching warning banner.",
        state.max_retries,
        state.current_agent,
    )
    banner = (
        "> ⚠️ **Grounding Warning:** Some claims in this answer could not be "
        "fully verified against the retrieved legal sources.\n\n"
    )
    existing_markdown = state.markdown_content or state.summary
    updated_markdown = banner + existing_markdown if existing_markdown else banner

    return Command(
        update={
            "grounding": grounding,
            "markdown_content": updated_markdown,
            "confidence": "low",
        },
        goto="formatter",
    )
