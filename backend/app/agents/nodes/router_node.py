"""Supervisor router node — hybrid O(1) + LLM-planned dispatch.

The user selects a mode via frontend buttons (Deep Research, Draft,
Review, Reasoning) or implicitly defaults to Quick QA.  The supervisor
reads ``state.mode`` and assesses query complexity:

- **Fast-path** (O(1)): Simple queries → deterministic dict lookup,
  zero LLM calls, instant dispatch to the matching worker.
- **Planned-path**: Complex queries → LLM planner generates a
  multi-step ``ExecutionPlan``, dispatches to the first step.

This dual-path design ensures Quick QA has zero added latency while
complex drafting/research queries get intelligent multi-agent planning.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Literal, Optional

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.types import Command
from langsmith import traceable

from app.agents.prompts.planning_prompt import PLANNING_PROMPT
from app.agents.state import AgentState, ExecutionPlan, PlanStep
from app.agents.streaming import get_emitter
from app.core.config import settings

logger = logging.getLogger(__name__)


_LEGAL_INSTRUMENT_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])"
    r"(?P<name>"
    r"[A-Z][A-Za-z'’.-]*"
    r"(?:\s+(?:[A-Z][A-Za-z'’.-]*|of|the|and|for|to|by))*"
    r"\s+(?:Act|Ordinance|Law)"
    r")\b"
)

# These words may be capitalized only because they start the question or a
# clause. They are context, not part of a statutory instrument's short title.
_LEADING_INSTRUMENT_CONTEXT_WORDS = frozenset(
    {
        "are",
        "can",
        "could",
        "did",
        "do",
        "does",
        "in",
        "is",
        "may",
        "must",
        "should",
        "under",
        "was",
        "were",
        "what",
        "which",
        "will",
        "would",
    }
)


# ── Static mode configuration ────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ModeConfig:
    """Immutable routing configuration for a single query mode."""

    route: str
    task_type: str
    answer_mode: str
    target_corpus: str
    retrieval_depth: str
    legal_top_k: int = 5
    user_doc_top_k: int = 6
    requires_user_document: bool = False
    requires_template: bool = False


_MODE_CONFIG: dict[str, ModeConfig] = {
    "quick_qa": ModeConfig(
        route="quick_qa",
        task_type="qa",
        answer_mode="direct_answer",
        target_corpus="both",
        retrieval_depth="fast",
        legal_top_k=10,
        user_doc_top_k=10,
    ),
    "deep_research": ModeConfig(
        route="deep_research",
        task_type="research",
        answer_mode="research_memo",
        target_corpus="both",
        retrieval_depth="iterative",
        legal_top_k=10,
        user_doc_top_k=10,
    ),
    "drafting": ModeConfig(
        route="drafting",
        task_type="drafting",
        answer_mode="draft",
        target_corpus="templates",
        retrieval_depth="expanded",
        legal_top_k=10,
        user_doc_top_k=10,
        requires_template=True,
    ),
    "review": ModeConfig(
        route="review",
        task_type="review",
        answer_mode="review_report",
        target_corpus="user_document",
        retrieval_depth="none",
        legal_top_k=5,
        user_doc_top_k=8,
        requires_user_document=True,
    ),
    "reasoning": ModeConfig(
        route="reasoning",
        task_type="reasoning",
        answer_mode="issue_analysis",
        target_corpus="both",
        retrieval_depth="expanded",
        legal_top_k=10,
        user_doc_top_k=10,
    ),
}

# Default fallback for safety
_DEFAULT_MODE = "quick_qa"

# Valid agent names for plan step validation
_VALID_AGENTS = frozenset(
    {
        "quick_qa",
        "deep_research",
        "reasoning",
        "drafting",
        "review",
        "verify",
    }
)


# ── Planning LLM (lightweight, deterministic) ────────────────────

_planning_llm = ChatGoogleGenerativeAI(
    model=settings.LLM_MODEL_NAME,
    google_api_key=settings.GOOGLE_API_KEY,
    temperature=0.0,
    max_output_tokens=512,
)
_planning_chain = (
    ChatPromptTemplate.from_template(PLANNING_PROMPT)
    | _planning_llm
    | JsonOutputParser()
)


# ── Complexity assessment ────────────────────────────────────────


def _assess_complexity(state: AgentState) -> str:
    """Heuristic complexity assessment — O(1), no LLM call.

    Returns
    -------
    str
        ``"fast_path"``      — simple query, skip planning entirely.
        ``"needs_planning"`` — complex query, invoke LLM planner.
    """
    # Ablation override: force fast-path dispatch (no planning)
    if state.ablation_config.get("force_fast_path"):
        return "fast_path"

    mode = state.mode
    question = state.question.lower()

    # Rule 1: Explicit quick_qa mode → always fast-path
    if mode == "quick_qa":
        return "fast_path"

    # Rule 2: Review and verify are self-contained → fast-path
    if mode in ("review", "verify"):
        return "fast_path"

    # Rule 3: Drafting — check for complexity signals
    if mode == "drafting":
        complexity_signals = (
            "research",
            "analyze",
            "analyse",
            "compare",
            "considering",
            "based on",
            "according to",
            "legal implications",
            "comprehensive",
            "detailed analysis",
            "risk assessment",
            "multiple",
            "all relevant",
            "thorough",
        )
        if any(signal in question for signal in complexity_signals):
            return "needs_planning"
        return "fast_path"

    # Rule 4: Deep research → benefits from planning
    if mode == "deep_research":
        return "needs_planning"

    # Rule 5: Reasoning → may need research first
    if mode == "reasoning":
        return "needs_planning"

    return "fast_path"


# ── Plan generation ──────────────────────────────────────────────


async def _generate_plan(
    state: AgentState,
    config: ModeConfig,
) -> ExecutionPlan:
    """Use LLM to generate a multi-step execution plan.

    Falls back to a single-step fast-path plan on any failure.
    """
    try:
        raw: dict = await _planning_chain.ainvoke(
            {
                "mode": state.mode,
                "question": state.question,
                "has_documents": str(bool(state.document_ids)),
            }
        )

        steps = [
            PlanStep(
                agent=s["agent"],
                purpose=s.get("purpose", ""),
                depends_on=s.get("depends_on", []),
                config_overrides=s.get("config_overrides", {}),
            )
            for s in raw.get("steps", [])
            if isinstance(s, dict) and s.get("agent") in _VALID_AGENTS
        ]

        if not steps:
            logger.warning("Planner returned no valid steps; falling back.")
            return _fallback_plan(config, state.mode)

        # Cap at 3 steps for safety and latency control
        return ExecutionPlan(
            plan_type="planned",
            steps=steps[:3],
            reasoning=raw.get("reasoning", ""),
            estimated_complexity=raw.get("estimated_complexity", "medium"),
        )

    except Exception:
        logger.exception("LLM planning failed; falling back to fast-path.")
        return _fallback_plan(config, state.mode)


def _fallback_plan(config: ModeConfig, mode: str) -> ExecutionPlan:
    """Create a single-step fast-path plan as a safe fallback."""
    return ExecutionPlan(
        plan_type="fast_path",
        steps=[PlanStep(agent=config.route, purpose=f"Fallback for {mode}")],
        reasoning="Falling back to direct dispatch.",
        estimated_complexity="low",
    )


def _enforce_final_step_matches_mode(
    plan: ExecutionPlan,
    config: ModeConfig,
) -> ExecutionPlan:
    """Ensure the plan's final step is the agent matching the user's mode.

    If the LLM planner produces a plan where the last step doesn't match
    the user's selected mode, this function corrects it by:
    1. If the mode's agent is already in the plan but not last → reorder
    2. If the mode's agent is missing entirely → append it as the final step

    The plan is capped at 3 steps after correction.
    """
    if not plan.steps:
        return plan

    target_agent = config.route
    last_agent = plan.steps[-1].agent

    if last_agent == target_agent:
        return plan  # Already correct

    logger.warning(
        "Plan's last step '%s' doesn't match user mode '%s'. Correcting.",
        last_agent,
        target_agent,
    )

    # Check if the target agent is already in the plan (just not last)
    existing_idx = None
    for i, step in enumerate(plan.steps):
        if step.agent == target_agent:
            existing_idx = i
            break

    new_steps = list(plan.steps)

    if existing_idx is not None:
        # Move the existing step to the end
        target_step = new_steps.pop(existing_idx)
        target_step = PlanStep(
            agent=target_step.agent,
            purpose=target_step.purpose,
            depends_on=[s.agent for s in new_steps],
            config_overrides=target_step.config_overrides,
        )
        new_steps.append(target_step)
    else:
        # Append the mode's agent as a new final step
        new_steps.append(
            PlanStep(
                agent=target_agent,
                purpose=f"Final {target_agent} output matching user's selected mode.",
                depends_on=[s.agent for s in new_steps],
            )
        )

    # Cap at 3 steps
    return ExecutionPlan(
        plan_type=plan.plan_type,
        steps=new_steps[:3],
        reasoning=plan.reasoning + f" [Corrected: final step → {target_agent}]",
        estimated_complexity=plan.estimated_complexity,
    )


# ── Supervisor router node ───────────────────────────────────────


@traceable(name="SupervisorRouter", metadata={"routing_method": "hybrid"})
async def router_node(
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
    """Supervisor router — dual-path: fast-path O(1) or LLM-planned.

    1. Assess complexity (heuristic, O(1))
    2. Fast-path: deterministic dispatch (same as before)
    3. Planned-path: LLM generates ExecutionPlan → dispatch to first agent
    """

    emitter = get_emitter(config)
    emitter.emit_step_start("supervisor", "Analysing your legal question")

    mode = state.mode or _DEFAULT_MODE
    config = _MODE_CONFIG.get(mode)

    if config is None:
        logger.error("Unknown mode '%s' — falling back to quick_qa.", mode)
        config = _MODE_CONFIG[_DEFAULT_MODE]
        mode = _DEFAULT_MODE

    emitter.emit_step_detail(
        "supervisor",
        f"Identified as a {config.task_type} task "
        f"({config.answer_mode.replace('_', ' ')} mode)",
    )

    has_documents = bool(state.document_ids)

    logger.info(
        "supervisor_dispatch: mode=%s route=%s has_docs=%s question_len=%d",
        mode,
        config.route,
        has_documents,
        len(state.question),
    )

    # ── Handle review without documents — request upload ──
    if config.requires_user_document and not has_documents:
        emitter.emit_step_done(
            "supervisor",
            "A document is required before the review can begin",
            route="formatter",
        )
        return Command(
            update={
                "route": config.route,
                "task_type": config.task_type,
                "answer_mode": config.answer_mode,
                "target_corpus": config.target_corpus,
                "route_confidence": "high",
                "routing_reason": f"User selected '{mode}' mode.",
                "needs_clarification": True,
                "clarification_question": (
                    "Please upload or attach the document you want reviewed."
                ),
                "summary": "Please upload or attach the document you want reviewed.",
                "confidence": "low",
                "current_agent": "router",
            },
            goto="formatter",
        )

    # ── Build retrieval plan ──
    retrieval = _build_retrieval_plan(state, config)

    # ── Assess complexity ──
    path = _assess_complexity(state)

    # ── Common routing metadata ──
    base_update = {
        "route": config.route,
        "task_type": config.task_type,
        "answer_mode": config.answer_mode,
        "target_corpus": config.target_corpus,
        "route_confidence": "high",
        "use_legal_corpus": retrieval["use_legal_corpus"],
        "use_user_documents": retrieval["use_user_documents"],
        "legal_top_k": retrieval["legal_top_k"],
        "user_doc_top_k": retrieval["user_doc_top_k"],
        "year_filter": retrieval.get("year_filters"),
        "act_name_filter": retrieval.get("act_name_filters"),
    }

    if path == "fast_path":
        # ── FAST PATH: O(1) dispatch — same as current behavior ──
        logger.info("Fast-path dispatch → %s", config.route)
        emitter.emit_step_done(
            "supervisor",
            f"Supervisor selected {config.route.replace('_', ' ').title()} Agent",
            route=config.route,
            path="fast_path",
        )
        return Command(
            update={
                **base_update,
                "routing_reason": f"User selected '{mode}' mode (fast-path).",
                "current_agent": config.route,
                "planning_seconds": 0.0,
                "execution_plan": ExecutionPlan(
                    plan_type="fast_path",
                    steps=[PlanStep(agent=config.route, purpose=f"Direct {mode}")],
                    reasoning=f"Fast-path dispatch for {mode} mode.",
                    estimated_complexity="low",
                ),
            },
            goto=config.route,
        )

    # ── PLANNED PATH: LLM generates multi-step plan ──
    logger.info("Generating execution plan for complex '%s' query.", mode)
    emitter.emit_step_detail(
        "supervisor",
        "Complex query detected — generating execution plan",
    )
    plan_start = time.monotonic()
    plan = await _generate_plan(state, config)
    plan = _enforce_final_step_matches_mode(plan, config)
    planning_seconds = time.monotonic() - plan_start
    first_agent = plan.steps[0].agent

    logger.info(
        "Execution plan: type=%s steps=%s first_agent=%s planning_time=%.2fs",
        plan.plan_type,
        [s.agent for s in plan.steps],
        first_agent,
        planning_seconds,
    )

    planned_agents = [step.agent for step in plan.steps]
    emitter.emit_plan(plan.plan_type, planned_agents, plan.reasoning)
    emitter.emit_step_done(
        "supervisor",
        f"Execution plan: {' → '.join(planned_agents)}",
        route=first_agent,
        path="planned",
        planning_seconds=planning_seconds,
    )

    return Command(
        update={
            **base_update,
            "routing_reason": (
                f"Planned multi-step execution for '{mode}' mode: {plan.reasoning}"
            ),
            "current_agent": first_agent,
            "current_step_index": 0,
            "execution_plan": plan,
            "planning_seconds": planning_seconds,
        },
        goto=first_agent,
    )


# ── Retrieval plan builder ───────────────────────────────────────


def _extract_entities_from_query(
    question: str,
) -> tuple[list[int] | None, list[str] | None]:
    years = list(
        dict.fromkeys(
            int(year) for year in re.findall(r"\b(?:18|19|20)\d{2}\b", question)
        )
    )
    year_filters = years if years else None

    instruments: list[str] = []
    for match in _LEGAL_INSTRUMENT_PATTERN.finditer(question):
        words = match.group("name").split()
        if len(words) >= 3 and words[1].casefold() == "the":
            # Handles question/command prefixes such as "Can the ...",
            # "Under the ...", and "Compare the ..." without maintaining an
            # unbounded list of possible opening verbs.
            words = words[2:]
        elif words and words[0].casefold() in _LEADING_INSTRUMENT_CONTEXT_WORDS:
            words.pop(0)
            if words and words[0].casefold() == "the":
                words.pop(0)
        elif words and words[0] == "The":
            words.pop(0)

        # A suffix by itself (for example, "What Act") is not a named legal
        # instrument and must not constrain retrieval.
        if len(words) < 2:
            continue

        instrument = " ".join(words)
        if instrument not in instruments:
            instruments.append(instrument)

    act_name_filters = instruments if instruments else None

    return year_filters, act_name_filters


def _build_retrieval_plan(state: AgentState, config: ModeConfig) -> dict:
    """Build a flat dict describing what to retrieve and from where.

    Combines the static mode config with runtime context (e.g. whether
    user documents are attached, document-summary detection).
    """
    has_documents = bool(state.document_ids)
    year_filters, act_name_filters = _extract_entities_from_query(state.question)

    # Document-summary requests — user docs only, broader retrieval
    if has_documents and _is_document_summary_query(state.question):
        return {
            "use_legal_corpus": False,
            "use_user_documents": True,
            "legal_top_k": 0,
            "user_doc_top_k": 8,
            "year_filters": None,
            "act_name_filters": None,
        }

    # Review / Drafting with documents — search both corpora
    if config.route in {"review", "drafting"} and has_documents:
        return {
            "use_legal_corpus": True,
            "use_user_documents": True,
            "legal_top_k": config.legal_top_k,
            "user_doc_top_k": config.user_doc_top_k,
            "year_filters": year_filters,
            "act_name_filters": act_name_filters,
        }

    # User documents explicitly targeted
    if config.target_corpus == "user_document" and has_documents:
        return {
            "use_legal_corpus": False,
            "use_user_documents": True,
            "legal_top_k": 0,
            "user_doc_top_k": config.user_doc_top_k,
            "year_filters": None,
            "act_name_filters": None,
        }

    # Deep research with documents — both corpora, no filters
    if config.task_type == "research" and has_documents:
        return {
            "use_legal_corpus": True,
            "use_user_documents": True,
            "legal_top_k": config.legal_top_k,
            "user_doc_top_k": config.user_doc_top_k,
            "year_filters": year_filters,
            "act_name_filters": act_name_filters,
        }

    # Default — legal corpus only (or with docs for reasoning)
    return {
        "use_legal_corpus": True,
        "use_user_documents": has_documents and config.route not in {"quick_qa"},
        "legal_top_k": config.legal_top_k,
        "user_doc_top_k": config.user_doc_top_k if has_documents else 0,
        "year_filters": year_filters,
        "act_name_filters": act_name_filters,
    }


# ── Helpers ──────────────────────────────────────────────────────


def _is_document_summary_query(question: str) -> bool:
    text = question.lower()
    return any(
        phrase in text
        for phrase in (
            "summarize this",
            "summarise this",
            "summary of this",
            "summarize the document",
            "summarise the document",
            "what does this document say",
        )
    )
