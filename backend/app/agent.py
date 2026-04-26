from __future__ import annotations

import logging

from app.schemas.responses import ConfidenceLevel, LegalResponse
from app.services.retrieval_service import RetrievalService
from app.services.context_assembler import ContextAssembler
from app.services.generation_service import GenerationService
from app.services.citation_verifier import CitationVerifier

logger = logging.getLogger(__name__)

# Initialise all services once at module load
_retrieval = RetrievalService()
_assembler = ContextAssembler()
_generator = GenerationService()
_verifier = CitationVerifier()


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
