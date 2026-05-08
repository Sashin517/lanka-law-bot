from __future__ import annotations

import logging
from langsmith import traceable

from app.schemas.responses import ConfidenceLevel, LegalResponse, RouteMetadata
from app.services.retrieval_service import RetrievalService
from app.services.context_assembler import ContextAssembler
from app.services.generation_service import GenerationService
from app.services.citation_verifier import CitationVerifier
from app.services.intent_routing import IntentRoute, SemanticIntentRouter
from app.services.intent_routing.models import IntentRoutePlan

logger = logging.getLogger(__name__)

# Initialise all services once at module load
_retrieval = RetrievalService()
_assembler = ContextAssembler()
_generator = GenerationService()
_verifier = CitationVerifier()
_router = SemanticIntentRouter()


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
async def process_query_with_route(question: str) -> tuple[LegalResponse, RouteMetadata]:
    router_result = await _router.classify(question)
    route = _route_metadata(router_result.plan)

    logger.info(
        "Intent route selected: route=%s task=%s confidence=%s source=%s",
        route.route,
        route.task_type,
        route.confidence,
        router_result.source,
    )

    if router_result.plan.route == IntentRoute.UNSUPPORTED:
        return _unsupported_response(route), route

    if router_result.plan.needs_clarification:
        return _clarification_response(route), route

    if router_result.plan.route == IntentRoute.REVIEW:
        review_route = route.model_copy(
            update={
                "needs_clarification": True,
                "clarification_question": (
                    "Document review is classified correctly, but this version "
                    "does not yet accept reviewable document text or uploads."
                ),
            }
        )
        return _clarification_response(review_route), review_route

    response = await process_legal_query(question)
    response.route = route
    return response, route


@traceable(name="LegalRAGPipeline")
async def process_legal_query(question: str) -> LegalResponse:
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

    # Step 1: Retrieve (hybrid + re-rank + parent expansion)
    results = _retrieval.search(
        query=question,
        top_k=5,
        expand_parents=True,
    )

    if not results:
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
    context_str, citation_map = _assembler.assemble(results)
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
