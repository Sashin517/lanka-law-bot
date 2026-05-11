"""Reasoning worker node — IRAC legal analysis engine.

Pipeline:
  1. Expanded retrieval (top_k=8) for comprehensive legal context
  2. Optionally retrieve user documents when document_ids present
  3. Assemble context with citation anchors
  4. Generate IRAC analysis via chain-of-thought prompt
  5. Verify citations

Handles applicability questions, liability analysis, enforceability
assessments, and legal risk evaluation using the Issue-Rule-Application-
Conclusion framework.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langsmith import traceable

from app.agents.state import AgentState, CitedClaim, SourceChunk
from app.agents.prompts.reasoning_prompt import REASONING_PROMPT
from app.core.config import settings
from app.schemas.responses import (
    CitedClaim as SchemaCitedClaim,
    ConfidenceLevel,
    LegalResponse,
    SourceReference,
)
from app.services.retrieval_service import RetrievalService
from app.services.context_assembler import MultiSourceContextAssembler
from app.services.citation_verifier import CitationVerifier
from app.services.user_document_retrieval_service import UserDocumentRetrievalService

logger = logging.getLogger(__name__)

# Shared singletons
_retrieval = RetrievalService()
_assembler = MultiSourceContextAssembler()
_verifier = CitationVerifier()

# Reasoning LLM — uses the main model for chain-of-thought capability
_reasoning_llm = ChatGoogleGenerativeAI(
    model=settings.LLM_MODEL_NAME,
    google_api_key=settings.GOOGLE_API_KEY,
    temperature=settings.LLM_TEMPERATURE,
    max_output_tokens=settings.LLM_MAX_TOKENS,
)
_reasoning_chain = (
    ChatPromptTemplate.from_template(REASONING_PROMPT)
    | _reasoning_llm
    | JsonOutputParser()
)

# Expanded top_k for reasoning — broader context than Quick QA
_REASONING_TOP_K = 8


@lru_cache(maxsize=1)
def _user_doc_retrieval() -> UserDocumentRetrievalService:
    """Lazy-load user-document retrieval service."""
    return UserDocumentRetrievalService()


@traceable(name="ReasoningNode")
async def reasoning_node(state: AgentState) -> dict:
    """Execute the IRAC legal analysis pipeline.

    Uses expanded retrieval (top_k=8) to gather broader context,
    then generates structured Issue-Rule-Application-Conclusion analysis.
    """

    # ── Step 1: Expanded retrieval from legal corpus ──
    legal_results: list[dict] = []
    if state.use_legal_corpus:
        legal_results = _retrieval.search(
            query=state.question,
            top_k=_REASONING_TOP_K,
            expand_parents=True,
            # No entity filters — reasoning needs broad context
        )

    # ── Step 2: User document retrieval (if applicable) ──
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
            logger.exception("User-document retrieval failed in reasoning_node.")

    # Handle empty retrieval
    if not legal_results and not user_doc_results:
        logger.warning("No retrieval results for reasoning: '%s'", state.question[:80])
        return {
            "summary": (
                "No relevant legal documents were found to perform this "
                "analysis. Please try rephrasing your question or using "
                "more specific legal terminology."
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
        "Reasoning context assembled: %d sources, %d chars.",
        len(citation_map), len(context_str),
    )

    # ── Step 4: Generate IRAC analysis ──
    try:
        raw: dict = await _reasoning_chain.ainvoke({
            "question": state.question,
            "context": context_str,
        })
    except Exception:
        logger.exception("Reasoning LLM generation failed.")
        raw = {
            "summary": (
                "The AI analysis service is temporarily unavailable. "
                "Below are the most relevant source excerpts."
            ),
            "analysis": [],
            "confidence": "low",
        }

    # ── Step 5: Build response and verify citations ──
    analysis_items = [
        SchemaCitedClaim(
            statement=item.get("statement", ""),
            citation_ids=item.get("citation_ids", []),
        )
        for item in raw.get("analysis", [])
        if isinstance(item, dict)
    ]

    confidence = raw.get("confidence", "medium")
    if confidence not in {e.value for e in ConfidenceLevel}:
        confidence = "medium"

    response = LegalResponse(
        summary=raw.get("summary", ""),
        analysis=analysis_items,
        sources=list(citation_map.values()),
        confidence=confidence,
    )
    response = _verifier.verify(response)

    # ── Step 6: Convert to agent state format ──
    sources = _to_source_chunks(citation_map)
    analysis = [
        CitedClaim(statement=c.statement, citation_ids=c.citation_ids)
        for c in response.analysis
    ]

    logger.info(
        "Reasoning complete: %d sources, %d IRAC claims, confidence=%s.",
        len(sources), len(analysis),
        response.confidence if isinstance(response.confidence, str)
        else response.confidence.value,
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


# ── Helpers ───────────────────────────────────────────────────────


def _to_source_chunks(
    citation_map: dict[str, SourceReference],
) -> list[SourceChunk]:
    """Convert citation map into agent-state SourceChunks."""
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
