"""Router node — deterministic mode-based dispatch.

The user selects a mode via frontend buttons (Deep Research, Draft,
Review, Reasoning) or implicitly defaults to Quick QA.  The router
reads ``state.mode``, looks up the static configuration, builds a
retrieval plan, and dispatches to the correct worker node via
``Command(goto=…)``.

No LLM call — O(1) dictionary lookup, 0 ms latency, 100% accuracy.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Literal

from langsmith import traceable
from langgraph.types import Command

from app.agents.state import AgentState

logger = logging.getLogger(__name__)


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
        legal_top_k=5,
        user_doc_top_k=6,
    ),
    "deep_research": ModeConfig(
        route="deep_research",
        task_type="research",
        answer_mode="research_memo",
        target_corpus="both",
        retrieval_depth="iterative",
        legal_top_k=5,
        user_doc_top_k=8,
    ),
    "drafting": ModeConfig(
        route="drafting",
        task_type="drafting",
        answer_mode="draft",
        target_corpus="templates",
        retrieval_depth="expanded",
        legal_top_k=5,
        user_doc_top_k=8,
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
        legal_top_k=5,
        user_doc_top_k=8,
    ),
}

# Default fallback for safety
_DEFAULT_MODE = "quick_qa"


# ── Router node ──────────────────────────────────────────────────


@traceable(name="RouterNode", metadata={"routing_method": "explicit_mode"})
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
        "formatter",
    ]
]:
    """Deterministic dispatch based on user-selected mode.

    Reads ``state.mode`` → looks up ``_MODE_CONFIG`` → builds retrieval
    plan → dispatches to the matching worker node via ``Command(goto=…)``.
    """

    mode = state.mode or _DEFAULT_MODE
    config = _MODE_CONFIG.get(mode)

    if config is None:
        logger.error("Unknown mode '%s' — falling back to quick_qa.", mode)
        config = _MODE_CONFIG[_DEFAULT_MODE]
        mode = _DEFAULT_MODE

    has_documents = bool(state.document_ids)

    logger.info(
        "mode_dispatch: mode=%s route=%s has_docs=%s question_len=%d",
        mode,
        config.route,
        has_documents,
        len(state.question),
    )

    # ── Handle review without documents — request upload ──
    if config.requires_user_document and not has_documents:
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

    # ── Dispatch to worker ──
    return Command(
        update={
            "route": config.route,
            "task_type": config.task_type,
            "answer_mode": config.answer_mode,
            "target_corpus": config.target_corpus,
            "route_confidence": "high",
            "routing_reason": f"User selected '{mode}' mode.",
            "current_agent": config.route,
            # Retrieval plan fields consumed by workers
            "use_legal_corpus": retrieval["use_legal_corpus"],
            "use_user_documents": retrieval["use_user_documents"],
            "legal_top_k": retrieval["legal_top_k"],
            "user_doc_top_k": retrieval["user_doc_top_k"],
            "year_filter": retrieval["year_filter"],
            "act_name_filter": retrieval["act_name_filter"],
        },
        goto=config.route,
    )


# ── Retrieval plan builder ───────────────────────────────────────


def _build_retrieval_plan(state: AgentState, config: ModeConfig) -> dict:
    """Build a flat dict describing what to retrieve and from where.

    Combines the static mode config with runtime context (e.g. whether
    user documents are attached, document-summary detection).
    """
    has_documents = bool(state.document_ids)

    # Document-summary requests — user docs only, broader retrieval
    if has_documents and _is_document_summary_query(state.question):
        return {
            "use_legal_corpus": False,
            "use_user_documents": True,
            "legal_top_k": 0,
            "user_doc_top_k": 8,
            "year_filter": None,
            "act_name_filter": None,
        }

    # Review / Drafting with documents — search both corpora
    if config.route in {"review", "drafting"} and has_documents:
        return {
            "use_legal_corpus": True,
            "use_user_documents": True,
            "legal_top_k": config.legal_top_k,
            "user_doc_top_k": config.user_doc_top_k,
            "year_filter": None,
            "act_name_filter": None,
        }

    # User documents explicitly targeted
    if config.target_corpus == "user_document" and has_documents:
        return {
            "use_legal_corpus": False,
            "use_user_documents": True,
            "legal_top_k": 0,
            "user_doc_top_k": config.user_doc_top_k,
            "year_filter": None,
            "act_name_filter": None,
        }

    # Deep research with documents — both corpora, no filters
    if config.task_type == "research" and has_documents:
        return {
            "use_legal_corpus": True,
            "use_user_documents": True,
            "legal_top_k": config.legal_top_k,
            "user_doc_top_k": config.user_doc_top_k,
            "year_filter": None,
            "act_name_filter": None,
        }

    # Default — legal corpus only (or with docs for reasoning)
    return {
        "use_legal_corpus": True,
        "use_user_documents": has_documents and config.route not in {"quick_qa"},
        "legal_top_k": config.legal_top_k,
        "user_doc_top_k": config.user_doc_top_k if has_documents else 0,
        "year_filter": None,
        "act_name_filter": None,
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
