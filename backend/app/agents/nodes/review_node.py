"""Review worker node — document risk analyzer.

Pipeline:
  1. Guard: require document_ids (return clarification if absent)
  2. Retrieve user document chunks from Qdrant
  3. Cross-reference against legal corpus from ChromaDB
  4. Assemble dual-source context with [DOC-*] and [LAW-*] anchors
  5. Generate clause-by-clause risk report
  6. Verify citations

Requires user-uploaded documents.  If none are attached, the router
should have already handled this, but a guard is included for safety.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langsmith import traceable

from app.agents.state import AgentState, CitedClaim, SourceChunk
from app.agents.prompts.review_prompt import REVIEW_PROMPT
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

# Review LLM — uses main model for cross-referencing capability
_review_llm = ChatGoogleGenerativeAI(
    model=settings.LLM_MODEL_NAME,
    google_api_key=settings.GOOGLE_API_KEY,
    temperature=settings.LLM_TEMPERATURE,
    max_output_tokens=settings.LLM_MAX_TOKENS,
)
_review_chain = (
    ChatPromptTemplate.from_template(REVIEW_PROMPT)
    | _review_llm
    | JsonOutputParser()
)

# Broader user-doc retrieval for thorough review
_REVIEW_USER_DOC_TOP_K = 8


@lru_cache(maxsize=1)
def _user_doc_retrieval() -> UserDocumentRetrievalService:
    """Lazy-load user-document retrieval service."""
    return UserDocumentRetrievalService()


@traceable(name="ReviewNode")
async def review_node(state: AgentState) -> dict:
    """Execute the document review pipeline.

    Retrieves user doc chunks → cross-references legal corpus →
    generates risk report.
    """

    # ── Guard: require document_ids ──
    if not state.document_ids:
        logger.warning("Review node invoked without document_ids.")
        return {
            "summary": "Please upload or attach the document you want reviewed.",
            "analysis": [],
            "retrieved_sources": [],
            "context_str": "",
            "confidence": "low",
            "needs_clarification": True,
            "clarification_question": (
                "Please upload or attach the document you want reviewed."
            ),
        }

    # ── Step 1: Retrieve user document chunks (primary source) ──
    user_doc_results: list[dict] = []
    try:
        user_doc_results = _user_doc_retrieval().search(
            query=state.question,
            document_ids=state.document_ids,
            matter_id=state.matter_id,
            top_k=_REVIEW_USER_DOC_TOP_K,
            expand_parents=True,
        )
    except Exception:
        logger.exception("User-document retrieval failed in review_node.")

    # ── Step 2: Cross-reference against legal corpus ──
    legal_results: list[dict] = []
    if state.use_legal_corpus:
        legal_results = _retrieval.search(
            query=state.question,
            top_k=state.legal_top_k,
            expand_parents=True,
        )

    # Handle empty retrieval
    if not user_doc_results and not legal_results:
        logger.warning("No retrieval results for review: '%s'", state.question[:80])
        return {
            "summary": (
                "No document content or legal references were retrieved. "
                "Please ensure the document has been uploaded and processed."
            ),
            "analysis": [],
            "retrieved_sources": [],
            "context_str": "",
            "confidence": "low",
        }

    # ── Step 3: Assemble dual-source context ──
    context_str, citation_map = _assembler.assemble(
        legal_results=legal_results,
        user_document_results=user_doc_results,
    )
    logger.info(
        "Review context assembled: %d sources, %d chars.",
        len(citation_map), len(context_str),
    )

    # ── Step 4: Generate risk report ──
    try:
        raw: dict = await _review_chain.ainvoke({
            "question": state.question,
            "context": context_str,
        })
    except Exception:
        logger.exception("Review LLM generation failed.")
        raw = {
            "summary": (
                "The AI review service is temporarily unavailable. "
                "Please try again shortly."
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
        "Review complete: %d user-doc sources, %d legal sources, %d findings.",
        sum(1 for s in sources if s.source_type == "user_document"),
        sum(1 for s in sources if s.source_type == "legal_authority"),
        len(analysis),
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
