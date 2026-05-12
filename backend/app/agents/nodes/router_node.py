"""Router node — fast intent classification and retrieval planning.

Reuses the existing ``SemanticIntentRouter`` (LLM-first with rule-based
fallback) and the ``_build_retrieval_plan`` logic from ``app.agent``.
Writes routing metadata + a retrieval plan into the shared state, then
uses ``Command(goto=…)`` to dispatch to the correct worker node.
"""

from __future__ import annotations

import logging
import re
from typing import Literal

from langsmith import traceable
from langgraph.types import Command

from app.agents.state import AgentState
from app.services.intent_routing import (
    IntentRoute,
    IntentRoutePlan,
    LegalTaskType,
    SemanticIntentRouter,
    TargetCorpus,
)

logger = logging.getLogger(__name__)

# Singleton — reuse across all graph invocations
_router = SemanticIntentRouter()

# Maps IntentRoute enum values to LangGraph node names
_ROUTE_TO_NODE: dict[str, str] = {
    "quick_qa": "quick_qa",
    "deep_research": "deep_research",
    "drafting": "drafting",
    "reasoning": "reasoning",
    "review": "review",
    "unsupported": "unsupported",
}


@traceable(name="RouterNode")
async def router_node(
    state: AgentState,
) -> Command[
    Literal[
        "quick_qa",
        "deep_research",
        "reasoning",
        "drafting",
        "review",
        "verify",
        "unsupported",
        "formatter",
    ]
]:
    """Classify intent, build retrieval plan, and dispatch to a worker."""

    # ── Step 1: Classify intent via LLM + fallback ──
    router_result = await _router.classify(state.question)
    plan = router_result.plan

    logger.info(
        "Router: route=%s task=%s confidence=%s source=%s",
        plan.route.value,
        plan.task_type.value,
        plan.confidence.value,
        router_result.source,
    )

    # ── Step 2: Handle early exits ──

    has_user_documents = bool(state.document_ids)

    # Review route without documents — request upload
    if plan.route == IntentRoute.REVIEW and not has_user_documents:
        return Command(
            update={
                "route": plan.route.value,
                "task_type": plan.task_type.value,
                "answer_mode": plan.answer_mode.value,
                "target_corpus": plan.target_corpus.value,
                "route_confidence": plan.confidence.value,
                "routing_reason": plan.routing_reason,
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

    # Clarification needed — skip worker, except when a review document is already attached.
    if plan.needs_clarification and not (
        plan.route == IntentRoute.REVIEW and has_user_documents
    ):
        return Command(
            update={
                "route": plan.route.value,
                "task_type": plan.task_type.value,
                "answer_mode": plan.answer_mode.value,
                "target_corpus": plan.target_corpus.value,
                "route_confidence": plan.confidence.value,
                "routing_reason": plan.routing_reason,
                "needs_clarification": True,
                "clarification_question": plan.clarification_question,
                "summary": plan.clarification_question
                or (
                    "Please provide more detail so the system can "
                    "route this legal query correctly."
                ),
                "confidence": "low",
                "current_agent": "router",
            },
            goto="formatter",
        )

    if plan.needs_clarification and plan.route == IntentRoute.REVIEW:
        logger.info(
            "Router clarification bypassed for review because %d document(s) are attached.",
            len(state.document_ids),
        )

    # ── Step 3: Build retrieval plan ──
    retrieval_plan = _build_retrieval_plan(
        question=state.question,
        route_plan=plan,
        document_ids=state.document_ids,
    )

    # ── Step 4: Detect explicit verify requests ──
    target = _ROUTE_TO_NODE.get(plan.route.value, "quick_qa")
    if _is_verify_request(state.question):
        target = "verify"  # User-triggered citation verification

    # ── Step 5: Dispatch via Command ──
    return Command(
        update={
            "route": plan.route.value,
            "task_type": plan.task_type.value,
            "answer_mode": plan.answer_mode.value,
            "target_corpus": plan.target_corpus.value,
            "route_confidence": plan.confidence.value,
            "routing_reason": plan.routing_reason,
            "entities": plan.entities.model_dump(),
            "current_agent": target,
            # Retrieval plan fields consumed by workers
            "use_legal_corpus": retrieval_plan["use_legal_corpus"],
            "use_user_documents": retrieval_plan["use_user_documents"],
            "legal_top_k": retrieval_plan["legal_top_k"],
            "user_doc_top_k": retrieval_plan["user_doc_top_k"],
            "year_filter": retrieval_plan["year_filter"],
            "act_name_filter": retrieval_plan["act_name_filter"],
        },
        goto=target,
    )


# ── Helpers (mirrored from app.agent) ────────────────────────────


def _build_retrieval_plan(
    question: str,
    route_plan: IntentRoutePlan,
    document_ids: list[str],
) -> dict:
    """Build a flat dict describing what to retrieve and from where.

    This mirrors the logic in ``app.agent._build_retrieval_plan`` but
    returns a plain dict so it can be merged into the shared AgentState.
    """
    year_filter, act_name_filter = _extract_entity_filters(route_plan)
    has_documents = bool(document_ids)

    # No user documents attached — legal corpus only
    if not has_documents:
        return {
            "use_legal_corpus": route_plan.route != IntentRoute.UNSUPPORTED,
            "use_user_documents": False,
            "legal_top_k": 5,
            "user_doc_top_k": 6,
            "year_filter": year_filter,
            "act_name_filter": act_name_filter,
        }

    # Document-summary request — user docs only, broader retrieval
    if _is_document_summary_query(question):
        return {
            "use_legal_corpus": False,
            "use_user_documents": True,
            "legal_top_k": 0,
            "user_doc_top_k": 8,
            "year_filter": None,
            "act_name_filter": None,
        }

    # Review / Drafting — search both corpora
    if route_plan.route in {IntentRoute.REVIEW, IntentRoute.DRAFTING}:
        return {
            "use_legal_corpus": True,
            "use_user_documents": True,
            "legal_top_k": 5,
            "user_doc_top_k": 8,
            "year_filter": year_filter,
            "act_name_filter": act_name_filter,
        }

    # Router explicitly targeted user documents
    if route_plan.target_corpus == TargetCorpus.USER_DOCUMENT:
        return {
            "use_legal_corpus": False,
            "use_user_documents": True,
            "legal_top_k": 0,
            "user_doc_top_k": 8,
            "year_filter": None,
            "act_name_filter": None,
        }

    # QA with docs — legal corpus preferred, user docs skipped
    if route_plan.task_type == LegalTaskType.QA:
        return {
            "use_legal_corpus": True,
            "use_user_documents": False,
            "legal_top_k": 5,
            "user_doc_top_k": 6,
            "year_filter": year_filter,
            "act_name_filter": act_name_filter,
        }

    # Deep Research with docs — search both corpora for comprehensive coverage
    if route_plan.task_type == LegalTaskType.RESEARCH:
        return {
            "use_legal_corpus": True,
            "use_user_documents": has_documents,
            "legal_top_k": 5,
            "user_doc_top_k": 8,
            "year_filter": None,  # No filters — broad search for research
            "act_name_filter": None,
        }

    # Default: both corpora
    return {
        "use_legal_corpus": True,
        "use_user_documents": True,
        "legal_top_k": 5,
        "user_doc_top_k": 8,
        "year_filter": year_filter,
        "act_name_filter": act_name_filter,
    }


def _extract_entity_filters(
    route_plan: IntentRoutePlan,
) -> tuple[int | None, str | None]:
    """Extract year / act-name filters from router entities.

    Only applied for QUICK_QA with exactly one entity to avoid
    breaking broad retrieval routes.
    """
    if route_plan.route != IntentRoute.QUICK_QA:
        return None, None

    entities = route_plan.entities
    year_filter: int | None = None
    if len(entities.dates) == 1:
        try:
            year_filter = int(entities.dates[0])
        except (ValueError, IndexError):
            pass

    act_name_filter: str | None = None
    if len(entities.act_names) == 1:
        act_name_filter = entities.act_names[0]

    return year_filter, act_name_filter


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


def _is_verify_request(question: str) -> bool:
    """Detect explicit citation-verification requests."""
    text = question.lower()
    return bool(
        re.search(r"\bverify\b.*\b(section|act|clause|case)\b", text)
        or re.search(r"\b(is it true|does .+ say|confirm that)\b", text)
    )
