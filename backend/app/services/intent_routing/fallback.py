from __future__ import annotations

from app.services.intent_routing.models import (
    AnswerMode,
    IntentRoute,
    IntentRoutePlan,
    LegalQueryEntities,
    LegalTaskType,
    RetrievalDepth,
    RouteConfidence,
    TargetCorpus,
)
from app.services.intent_routing.normalizer import normalize_query
from app.services.intent_routing.rules import (
    DRAFTING_KEYWORDS,
    QUICK_QA_KEYWORDS,
    REASONING_KEYWORDS,
    RESEARCH_KEYWORDS,
    REVIEW_KEYWORDS,
    contains_any,
    extract_dates,
    extract_section_refs,
    has_section_reference,
)


def build_fallback_route_plan(question: str, reason: str) -> IntentRoutePlan:
    normalized = normalize_query(question)
    entities = LegalQueryEntities(
        section_refs=extract_section_refs(normalized),
        dates=extract_dates(normalized),
        jurisdiction="Sri Lanka",
    )

    route = IntentRoute.QUICK_QA
    task_type = LegalTaskType.QA
    target_corpus = TargetCorpus.BOTH
    answer_mode = AnswerMode.DIRECT_ANSWER
    retrieval_depth = RetrievalDepth.FAST
    confidence = RouteConfidence.LOW
    requires_user_document = False
    requires_template = False

    if contains_any(normalized, REVIEW_KEYWORDS):
        route = IntentRoute.REVIEW
        task_type = LegalTaskType.REVIEW
        target_corpus = TargetCorpus.USER_DOCUMENT
        answer_mode = AnswerMode.REVIEW_REPORT
        retrieval_depth = RetrievalDepth.NONE
        confidence = RouteConfidence.MEDIUM
        requires_user_document = True
    elif contains_any(normalized, DRAFTING_KEYWORDS):
        route = IntentRoute.DRAFTING
        task_type = LegalTaskType.DRAFTING
        target_corpus = TargetCorpus.TEMPLATES
        answer_mode = AnswerMode.DRAFT
        retrieval_depth = RetrievalDepth.EXPANDED
        confidence = RouteConfidence.MEDIUM
        requires_template = True
    elif contains_any(normalized, RESEARCH_KEYWORDS):
        route = IntentRoute.DEEP_RESEARCH
        task_type = LegalTaskType.RESEARCH
        target_corpus = TargetCorpus.BOTH
        answer_mode = AnswerMode.RESEARCH_MEMO
        retrieval_depth = RetrievalDepth.ITERATIVE
        confidence = RouteConfidence.MEDIUM
    elif contains_any(normalized, REASONING_KEYWORDS):
        route = IntentRoute.REASONING
        task_type = LegalTaskType.REASONING
        target_corpus = TargetCorpus.BOTH
        answer_mode = AnswerMode.ISSUE_ANALYSIS
        retrieval_depth = RetrievalDepth.EXPANDED
        confidence = RouteConfidence.MEDIUM
    elif contains_any(normalized, QUICK_QA_KEYWORDS) or has_section_reference(normalized):
        confidence = RouteConfidence.MEDIUM

    return IntentRoutePlan(
        raw_query=(question or " ").strip() or " ",
        normalized_query=normalized or (question or " ").strip() or " ",
        route=route,
        task_type=task_type,
        target_corpus=target_corpus,
        answer_mode=answer_mode,
        retrieval_depth=retrieval_depth,
        entities=entities,
        requires_user_document=requires_user_document,
        requires_template=requires_template,
        needs_clarification=False,
        clarification_question=None,
        confidence=confidence,
        routing_reason=reason,
    )
