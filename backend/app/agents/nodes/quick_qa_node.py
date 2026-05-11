"""Quick QA worker node — single-pass RAG pipeline.

Pipeline: Retrieve → Assemble → Generate → Verify citations.

Reuses the existing singleton services directly.  This is the fastest
agent path and handles specific act / clause / definition questions.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from langsmith import traceable

from app.agents.state import AgentState, CitedClaim, SourceChunk
from app.schemas.responses import LegalResponse, SourceReference
from app.services.retrieval_service import RetrievalService
from app.services.context_assembler import MultiSourceContextAssembler
from app.services.generation_service import GenerationService
from app.services.citation_verifier import CitationVerifier
from app.services.user_document_retrieval_service import UserDocumentRetrievalService

logger = logging.getLogger(__name__)

# Shared singletons — initialised once, reused across invocations
_retrieval = RetrievalService()
_assembler = MultiSourceContextAssembler()
_generator = GenerationService()
_verifier = CitationVerifier()


@lru_cache(maxsize=1)
def _user_doc_retrieval() -> UserDocumentRetrievalService:
    """Lazy-load the user-document retrieval service."""
    return UserDocumentRetrievalService()


@traceable(name="QuickQANode")
async def quick_qa_node(state: AgentState) -> dict:
    """Execute the single-pass RAG pipeline for fast legal lookups.

    Reads retrieval plan fields set by the router node and returns
    state updates for summary, analysis, sources, and confidence.
    """

    # ── Step 1: Retrieve from legal corpus ──
    legal_results: list[dict] = []
    if state.use_legal_corpus:
        legal_results = _retrieval.search(
            query=state.question,
            top_k=state.legal_top_k,
            expand_parents=True,
            year_filter=state.year_filter,
            act_name_filter=state.act_name_filter,
        )

    # ── Step 2: Retrieve from user documents (if applicable) ──
    user_doc_results: list[dict] = []
    if state.use_user_documents and state.document_ids:
        try:
            user_doc_results = _user_doc_retrieval().search(
                query=state.question,
                document_ids=state.document_ids,
                matter_id=state.matter_id,
                top_k=state.user_doc_top_k,
                expand_parents=True,
            )
        except Exception:
            logger.exception("User-document retrieval failed in quick_qa_node.")

    # Handle empty retrieval
    if not legal_results and not user_doc_results:
        logger.warning("No retrieval results for: '%s'", state.question[:80])
        return {
            "summary": (
                "No relevant legal documents were found for this query. "
                "Please try rephrasing your question or using more specific "
                "legal terminology."
            ),
            "analysis": [],
            "retrieved_sources": [],
            "context_str": "",
            "confidence": "low",
        }

    # ── Step 3: Assemble context with citation anchors ──
    context_str, citation_map = _assembler.assemble(
        legal_results=legal_results,
        user_document_results=user_doc_results,
    )
    logger.info(
        "QA context assembled: %d sources, %d chars.",
        len(citation_map),
        len(context_str),
    )

    # ── Step 4: Generate LLM response ──
    response: LegalResponse = await _generator.generate(
        state.question, context_str, citation_map,
    )

    # ── Step 5: Verify citations (strip hallucinated IDs) ──
    response = _verifier.verify(response)

    # ── Step 6: Convert to agent state format ──
    sources = _to_source_chunks(citation_map)
    analysis = _to_cited_claims(response.analysis)

    logger.info(
        "QA complete: confidence=%s, sources=%d, claims=%d",
        response.confidence, len(sources), len(analysis),
    )

    return {
        "retrieved_sources": sources,
        "context_str": context_str,
        "summary": response.summary,
        "analysis": analysis,
        "confidence": response.confidence
        if isinstance(response.confidence, str)
        else response.confidence.value,
    }


# ── Conversion helpers ────────────────────────────────────────────


def _to_source_chunks(
    citation_map: dict[str, SourceReference],
) -> list[SourceChunk]:
    """Convert the citation map into agent-state SourceChunks."""
    return [
        SourceChunk(
            citation_id=ref.citation_id,
            content=ref.excerpt,
            title=ref.title,
            section=ref.section,
            year=ref.year,
            breadcrumb=ref.breadcrumb,
            excerpt=ref.excerpt,
            source_type=ref.source_type or "legal_authority",
            document_id=ref.document_id,
            filename=ref.filename,
        )
        for ref in citation_map.values()
    ]


def _to_cited_claims(
    analysis: list,
) -> list[CitedClaim]:
    """Convert response analysis items into agent-state CitedClaims."""
    return [
        CitedClaim(
            statement=claim.statement,
            citation_ids=claim.citation_ids,
        )
        for claim in analysis
    ]
