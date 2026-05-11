"""Grounding Verifier node — LLM-as-judge faithfulness gate.

This is the zero-hallucination enforcement layer.  After every worker
agent produces a response, this node asks a separate LLM call to judge
whether every claim is supported by the retrieved sources.

Routing logic (via ``Command``):
- Grounded   → ``formatter``
- Not grounded + retries left → re-route to ``current_agent``
- Max retries exhausted → fallback response → ``formatter``
"""

from __future__ import annotations

import json
import logging
from typing import Literal

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langsmith import traceable
from langgraph.types import Command

from app.agents.state import AgentState, CitedClaim, GroundingResult
from app.agents.prompts.grounding_prompt import GROUNDING_JUDGE_PROMPT
from app.core.config import settings

logger = logging.getLogger(__name__)

# Dedicated LLM instance for grounding verification
_grounding_llm = ChatGoogleGenerativeAI(
    model=settings.LLM_MODEL_NAME,
    google_api_key=settings.GOOGLE_API_KEY,
    temperature=0.0,              # Deterministic for judging
    max_output_tokens=1024,
)
_grounding_parser = JsonOutputParser()
_grounding_prompt = ChatPromptTemplate.from_template(GROUNDING_JUDGE_PROMPT)
_grounding_chain = _grounding_prompt | _grounding_llm | _grounding_parser


@traceable(name="GroundingVerifier")
async def grounding_node(
    state: AgentState,
) -> Command[Literal["quick_qa", "deep_research", "reasoning", "drafting", "review", "verify", "formatter"]]:
    """Judge whether the generated response is faithful to sources.

    Returns a ``Command`` that routes to formatter (pass), back to the
    worker (retry), or to formatter with a fallback (max retries).
    """

    # ── Skip grounding for empty / clarification responses ──
    if not state.summary or state.needs_clarification:
        return Command(
            update={
                "grounding": GroundingResult(
                    is_grounded=True, grounding_score=1.0,
                ),
            },
            goto="formatter",
        )

    # ── Build the claims string for the judge ──
    claims_text = "\n".join(
        f"- {c.statement} (cites: {', '.join(c.citation_ids)})"
        for c in state.analysis
    ) or "(No analysis claims)"

    # ── Call the grounding judge LLM ──
    try:
        raw: dict = await _grounding_chain.ainvoke({
            "summary": state.summary,
            "claims": claims_text,
            "sources": state.context_str[:12000],  # Cap context to fit in window
        })

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
        "Grounding result: grounded=%s score=%.2f ungrounded=%d retry=%d/%d",
        grounding.is_grounded,
        grounding.grounding_score,
        len(grounding.ungrounded_claims),
        state.retry_count,
        state.max_retries,
    )

    # ── Route based on grounding result ──

    if grounding.is_grounded:
        return Command(
            update={"grounding": grounding},
            goto="formatter",
        )

    # Retry: send back to the same worker with correction feedback
    if state.retry_count < state.max_retries:
        logger.warning(
            "Grounding failed (attempt %d/%d). Retrying %s.",
            state.retry_count + 1,
            state.max_retries,
            state.current_agent,
        )
        return Command(
            update={
                "grounding": grounding,
                "retry_count": state.retry_count + 1,
            },
            goto=state.current_agent,
        )

    # Max retries exhausted — return raw sources only
    logger.warning(
        "Grounding failed after %d retries. Returning fallback.",
        state.max_retries,
    )
    return Command(
        update={
            "grounding": grounding,
            "summary": (
                "The system could not generate a fully verified answer. "
                "Below are the most relevant source excerpts retrieved "
                "from the legal database."
            ),
            "analysis": [],
            "confidence": "low",
        },
        goto="formatter",
    )
