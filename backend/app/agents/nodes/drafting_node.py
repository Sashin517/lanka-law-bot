"""Drafting worker node — template-aware legal document generator.

Pipeline:
  1. Select template based on answer_mode / document type detection
  2. Retrieve relevant statutes from legal corpus
  3. Optionally retrieve user document context when document_ids present
  4. Assemble dual-source context with [LAW-*] and [DOC-*] anchors
  5. Generate draft using template-injected prompt
  6. Verify citations
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langsmith import traceable

from app.agents.state import AgentState, CitedClaim, SourceChunk
from app.agents.prompts.drafting_prompt import DRAFTING_PROMPT
from app.agents.templates import TEMPLATE_REGISTRY
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

# Drafting LLM — uses main model for structured generation capability
_drafting_llm = ChatGoogleGenerativeAI(
    model=settings.LLM_MODEL_NAME,
    google_api_key=settings.GOOGLE_API_KEY,
    temperature=settings.LLM_TEMPERATURE,
    max_output_tokens=settings.LLM_MAX_TOKENS,
)
_drafting_parser = JsonOutputParser()

# Document-type detection patterns for template selection
_DOC_TYPE_PATTERNS: list[tuple[str, list[str]]] = [
    ("contract", ["contract", "agreement", "lease", "employment", "service agreement"]),
    ("pleading", ["plaint", "petition", "answer", "pleading", "court filing", "motion"]),
    ("notice", ["notice", "demand", "letter of demand", "quit notice", "termination notice"]),
    ("affidavit", ["affidavit", "sworn statement", "declaration", "deposition"]),
]


@lru_cache(maxsize=1)
def _user_doc_retrieval() -> UserDocumentRetrievalService:
    """Lazy-load user-document retrieval service."""
    return UserDocumentRetrievalService()


@traceable(name="DraftingNode")
async def drafting_node(state: AgentState) -> dict:
    """Execute the template-aware legal drafting pipeline.

    Selects template → retrieves → assembles → generates → verifies.
    """

    # ── Step 1: Select the appropriate template ──
    template_key = _select_template(state.question, state.answer_mode)
    template_text = TEMPLATE_REGISTRY.get(template_key, TEMPLATE_REGISTRY["contract"])
    logger.info("Drafting with template: '%s'", template_key)

    # ── Step 2: Retrieve from legal corpus ──
    legal_results: list[dict] = []
    if state.use_legal_corpus:
        legal_results = _retrieval.search(
            query=state.question,
            top_k=state.legal_top_k,
            expand_parents=True,
        )

    # ── Step 3: Retrieve from user documents (if applicable) ──
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
            logger.exception("User-document retrieval failed in drafting_node.")

    # Handle empty retrieval — drafting can still proceed with template
    if not legal_results and not user_doc_results:
        logger.warning("No retrieval results for drafting: '%s'", state.question[:80])
        # Drafting can still produce a template-based output, just lower confidence

    # ── Step 4: Assemble context with citation anchors ──
    context_str, citation_map = _assembler.assemble(
        legal_results=legal_results,
        user_document_results=user_doc_results,
    )
    logger.info(
        "Drafting context assembled: %d sources, %d chars.",
        len(citation_map), len(context_str),
    )

    # ── Step 5: Generate draft with template-injected prompt ──
    prompt = ChatPromptTemplate.from_template(DRAFTING_PROMPT)
    chain = prompt | _drafting_llm | _drafting_parser

    try:
        raw: dict = await chain.ainvoke({
            "question": state.question,
            "template": template_text,
            "context": context_str or "(No source documents available — use template structure only.)",
        })
    except Exception:
        logger.exception("Drafting LLM generation failed.")
        raw = {
            "summary": (
                "The AI drafting service is temporarily unavailable. "
                "Please try again shortly."
            ),
            "analysis": [],
            "confidence": "low",
        }

    # ── Step 6: Build response and verify citations ──
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

    # ── Step 7: Convert to agent state format ──
    sources = _to_source_chunks(citation_map)
    analysis = [
        CitedClaim(statement=c.statement, citation_ids=c.citation_ids)
        for c in response.analysis
    ]

    # Build the full draft text from analysis sections
    draft_content = "\n\n".join(c.statement for c in response.analysis)

    logger.info(
        "Drafting complete: template=%s, %d sources, %d sections.",
        template_key, len(sources), len(analysis),
    )

    return {
        "retrieved_sources": sources,
        "context_str": context_str,
        "summary": response.summary,
        "analysis": analysis,
        "draft_content": draft_content,
        "confidence": response.confidence
        if isinstance(response.confidence, str)
        else response.confidence.value,
    }


# ── Helpers ───────────────────────────────────────────────────────


def _select_template(question: str, answer_mode: str) -> str:
    """Choose the best template based on answer_mode or question keywords.

    Priority: explicit answer_mode match → keyword detection → default.
    """
    # Check if answer_mode directly maps to a template
    if answer_mode in TEMPLATE_REGISTRY:
        return answer_mode

    # Keyword-based detection from the question text
    text = question.lower()
    for template_key, keywords in _DOC_TYPE_PATTERNS:
        if any(kw in text for kw in keywords):
            return template_key

    # Default to contract (most common drafting request)
    return "contract"


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
