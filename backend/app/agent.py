from __future__ import annotations

import logging
from functools import lru_cache
from langsmith import traceable
from pydantic import BaseModel

from app.schemas.responses import ConfidenceLevel, LegalResponse, RouteMetadata
from app.services.retrieval_service import get_retrieval_service
from app.services.context_assembler import MultiSourceContextAssembler
from app.services.generation_service import GenerationService
from app.services.citation_verifier import CitationVerifier
from app.services.intent_routing import IntentRoute, SemanticIntentRouter
from app.services.intent_routing.models import IntentRoutePlan, LegalTaskType, TargetCorpus
from app.services.user_document_retrieval_service import UserDocumentRetrievalService

logger = logging.getLogger(__name__)

# Initialise all services once at module load
_retrieval = get_retrieval_service()
_assembler = MultiSourceContextAssembler()
_generator = GenerationService()
_verifier = CitationVerifier()
_router = SemanticIntentRouter()


class RetrievalPlan(BaseModel):
    use_legal_corpus: bool
    use_user_documents: bool
    legal_top_k: int = 5
    user_doc_top_k: int = 6
    # Optional metadata filters — only populated for narrow QUICK_QA queries
    year_filter: int | None = None
    act_name_filter: str | None = None


@lru_cache(maxsize=1)
def _user_document_retrieval() -> UserDocumentRetrievalService:
    return UserDocumentRetrievalService()


def _route_metadata(plan: IntentRoutePlan) -> RouteMetadata:
    return RouteMetadata(
        route=plan.route.value,
        task_type=plan.task_type.value,
        answer_mode=plan.answer_mode.value,
        target_corpus=plan.target_corpus.value,
        confidence=plan.confidence.value,
        needs_clarification=plan.needs_clarification,
        clarification_question=plan.clarification_question,
        routing_reason=plan.routing_reason,
    )


def _unsupported_response(route: RouteMetadata) -> LegalResponse:
    return LegalResponse(
        summary=(
            "This query is outside the supported Sri Lankan legal research scope "
            "for the current system."
        ),
        analysis=[],
        sources=[],
        confidence=ConfidenceLevel.LOW,
        route=route,
    )


def _clarification_response(route: RouteMetadata) -> LegalResponse:
    question = route.clarification_question or (
        "Please provide more detail so the system can route this legal query correctly."
    )
    return LegalResponse(
        summary=question,
        analysis=[],
        sources=[],
        confidence=ConfidenceLevel.LOW,
        route=route,
    )


@traceable(name="AgentOrchestrator")
async def process_query_with_route(
    question: str,
    document_ids: list[str] | None = None,
    matter_id: str | None = None,
) -> tuple[LegalResponse, RouteMetadata]:
    document_ids = document_ids or []
    router_result = await _router.classify(question)
    route = _route_metadata(router_result.plan)
    retrieval_plan = _build_retrieval_plan(
        question=question,
        route_plan=router_result.plan,
        document_ids=document_ids,
    )

    logger.info(
        "Intent route selected: route=%s task=%s confidence=%s source=%s legal=%s docs=%s",
        route.route,
        route.task_type,
        route.confidence,
        router_result.source,
        retrieval_plan.use_legal_corpus,
        retrieval_plan.use_user_documents,
    )

    if router_result.plan.route == IntentRoute.UNSUPPORTED:
        return _unsupported_response(route), route

    if router_result.plan.needs_clarification:
        return _clarification_response(route), route

    if router_result.plan.route == IntentRoute.REVIEW and not document_ids:
        review_route = route.model_copy(
            update={
                "needs_clarification": True,
                "clarification_question": (
                    "Please upload or attach the document you want reviewed."
                ),
            }
        )
        return _clarification_response(review_route), review_route

    response = await process_legal_query(
        question=question,
        retrieval_plan=retrieval_plan,
        document_ids=document_ids,
        matter_id=matter_id,
    )
    response.route = route
    return response, route


@traceable(name="LegalRAGPipeline")
async def process_legal_query(
    question: str,
    retrieval_plan: RetrievalPlan | None = None,
    document_ids: list[str] | None = None,
    matter_id: str | None = None,
) -> LegalResponse:
    """
    Full RAG pipeline:

        User Question
          → Hybrid Retrieval (Dense + BM25)
          → Cross-Encoder Re-Ranking
          → Parent Context Expansion
          → Citation-Anchored Context Assembly
          → Grounded LLM Generation (Gemini Flash)
          → Citation Verification
          → LegalResponse

    Parameters
    ----------
    question : str
        The user's raw legal question.

    Returns
    -------
    LegalResponse
        Structured response with summary, cited analysis, source
        references, confidence level, and legal disclaimer.
    """
    logger.info("Processing query: '%s'", question[:100])
    retrieval_plan = retrieval_plan or RetrievalPlan(
        use_legal_corpus=True,
        use_user_documents=False,
    )
    document_ids = document_ids or []

    legal_results: list[dict] = []
    user_document_results: list[dict] = []

    if retrieval_plan.use_legal_corpus:
        legal_results = _retrieval.search(
            query=question,
            top_k=retrieval_plan.legal_top_k,
            expand_parents=True,
            year_filter=retrieval_plan.year_filter,
            act_name_filter=retrieval_plan.act_name_filter,
        )

    if retrieval_plan.use_user_documents:
        try:
            user_document_results = _user_document_retrieval().search(
                query=question,
                document_ids=document_ids,
                matter_id=matter_id,
                top_k=retrieval_plan.user_doc_top_k,
                expand_parents=True,
            )
        except Exception:
            logger.exception("User-document retrieval failed.")
            user_document_results = []

    if retrieval_plan.use_user_documents and not user_document_results:
        logger.warning("No user document retrieval results for query: '%s'", question[:80])
        return LegalResponse(
            summary=(
                "No relevant uploaded document context was found for this query. "
                "Please confirm the document finished processing and try a more specific question."
            ),
            analysis=[],
            sources=[],
            confidence=ConfidenceLevel.LOW,
        )

    if not legal_results and not user_document_results:
        logger.warning("No retrieval results for query: '%s'", question[:80])
        return LegalResponse(
            summary=(
                "No relevant legal documents were found for this query. "
                "Please try rephrasing your question or using more specific "
                "legal terminology."
            ),
            analysis=[],
            sources=[],
            confidence=ConfidenceLevel.LOW,
        )

    # Step 2: Assemble context with citation anchors
    context_str, citation_map = _assembler.assemble(
        legal_results=legal_results,
        user_document_results=user_document_results,
    )
    logger.info(
        "Context assembled: %d sources, %d chars.",
        len(citation_map),
        len(context_str),
    )

    # Step 3: Generate LLM response
    response = await _generator.generate(question, context_str, citation_map)

    # Step 4: Verify citations
    response = _verifier.verify(response)

    logger.info(
        "Query processed: confidence=%s, sources=%d, claims=%d",
        response.confidence,
        len(response.sources),
        len(response.analysis),
    )
    return response


def _build_retrieval_plan(
    question: str,
    route_plan: IntentRoutePlan,
    document_ids: list[str],
) -> RetrievalPlan:
    # ── Entity-based metadata filters ──
    # Only apply for QUICK_QA with exactly one date/act to avoid
    # breaking DEEP_RESEARCH, REASONING, etc. that need broad retrieval.
    year_filter, act_name_filter = _extract_entity_filters(route_plan)

    has_documents = bool(document_ids)
    if not has_documents:
        return RetrievalPlan(
            use_legal_corpus=route_plan.route != IntentRoute.UNSUPPORTED,
            use_user_documents=False,
            year_filter=year_filter,
            act_name_filter=act_name_filter,
        )

    if _is_document_summary_query(question):
        return RetrievalPlan(
            use_legal_corpus=False,
            use_user_documents=True,
            legal_top_k=0,
            user_doc_top_k=8,
        )

    if route_plan.route in {IntentRoute.REVIEW, IntentRoute.DRAFTING}:
        return RetrievalPlan(
            use_legal_corpus=True,
            use_user_documents=True,
            legal_top_k=5,
            user_doc_top_k=8,
            year_filter=year_filter,
            act_name_filter=act_name_filter,
        )

    if route_plan.target_corpus == TargetCorpus.USER_DOCUMENT:
        return RetrievalPlan(
            use_legal_corpus=False,
            use_user_documents=True,
            legal_top_k=0,
            user_doc_top_k=8,
        )

    if route_plan.task_type in {LegalTaskType.QA, LegalTaskType.RESEARCH}:
        return RetrievalPlan(
            use_legal_corpus=True,
            use_user_documents=False,
            year_filter=year_filter,
            act_name_filter=act_name_filter,
        )

    return RetrievalPlan(
        use_legal_corpus=_mentions_legal_authority(question),
        use_user_documents=True,
        legal_top_k=5,
        user_doc_top_k=8,
        year_filter=year_filter,
        act_name_filter=act_name_filter,
    )


def _extract_entity_filters(
    route_plan: IntentRoutePlan,
) -> tuple[int | None, str | None]:
    """Extract year and act-name filters from router entities.

    Guard rails:
    - Only apply for QUICK_QA route (narrow, single-source lookups).
    - Only when exactly 1 date or 1 act name was extracted, so we
      don't accidentally exclude the second act in comparison queries.
    - DEEP_RESEARCH, REASONING, DRAFTING, and REVIEW never get filtered
      because they inherently require broad retrieval across multiple
      authorities.
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


def _mentions_legal_authority(question: str) -> bool:
    text = question.lower()
    return any(
        term in text
        for term in (
            "law",
            "legal",
            "sri lanka",
            "sri lankan",
            "act",
            "case",
            "court",
            "valid",
            "enforceable",
            "liability",
            "rights",
        )
    )
