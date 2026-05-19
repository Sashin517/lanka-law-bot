"""Review worker node — document risk analyzer.

Pipeline:
  1. Guard: require document_ids (return clarification if absent)
  2. Retrieve user document chunks from Qdrant
  3. Cross-reference against legal corpus from ChromaDB
  4. Assemble dual-source context with [DOC-*] and [LAW-*] anchors
  5. Generate clause-by-clause risk report (hybrid JSON + markdown)
  6. Verify citations via existing CitationVerifier

Requires user-uploaded documents.  If none are attached, the router
should have already handled this, but a guard is included for safety.
"""

from __future__ import annotations

import logging

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langsmith import traceable

from app.agents.state import AgentState
from app.agents.shared import (
    retrieval_service as _retrieval,
    context_assembler as _assembler,
    citation_verifier as _verifier,
    get_user_doc_retrieval,
)
from app.agents.prompts.review_prompt import REVIEW_PROMPT
from app.agents.nodes.helpers import (
    extract_first_paragraph,
    normalize_confidence,
    build_and_verify_sources,
    strip_invalid_anchors,
    to_source_chunks,
)
from app.core.config import settings

logger = logging.getLogger(__name__)

# Review LLM — uses main model for cross-referencing capability
_review_llm = ChatGoogleGenerativeAI(
    model=settings.LLM_MODEL_NAME,
    google_api_key=settings.GOOGLE_API_KEY,
    temperature=settings.LLM_TEMPERATURE,
    max_output_tokens=settings.LLM_MAX_TOKENS,
)
_review_chain = (
    ChatPromptTemplate.from_template(REVIEW_PROMPT) | _review_llm | JsonOutputParser()
)

# Broader user-doc retrieval for thorough review
_REVIEW_USER_DOC_TOP_K = 8


@traceable(name="ReviewNode")
async def review_node(state: AgentState) -> dict:
    """Execute the document review pipeline.

    Retrieves user doc chunks → cross-references legal corpus →
    generates risk report in markdown.
    """

    # ── Guard: require document_ids ──
    if not state.document_ids:
        logger.warning("Review node invoked without document_ids.")
        return {
            "summary": "Please upload or attach the document you want reviewed.",
            "markdown_content": (
                "## Document Required\n\n"
                "Please upload or attach the document you want reviewed."
            ),
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
        user_doc_results = get_user_doc_retrieval().search(
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
            "summary": "No document content or legal references were retrieved.",
            "markdown_content": (
                "## No Results\n\n"
                "No document content or legal references were retrieved. "
                "Please ensure the document has been uploaded and processed."
            ),
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

    # ── Step 4: Generate risk report (hybrid JSON) ──
    try:
        raw: dict = await _review_chain.ainvoke({
            "question": state.question,
            "context": context_str,
        })
    except Exception:
        logger.exception("Review LLM generation failed.")
        raw = {
            "report_markdown": (
                "The AI review service is temporarily unavailable. "
                "Please try again shortly."
            ),
            "confidence": "low",
            "sources_used": [],
            "risk_count": 0,
        }

    # ── Step 5: Verify citations via existing CitationVerifier ──
    markdown = raw.get("report_markdown", "")
    sources_used = raw.get("sources_used", [])

    valid_ids = build_and_verify_sources(sources_used, citation_map, _verifier)
    markdown = strip_invalid_anchors(markdown, valid_ids)

    confidence = normalize_confidence(raw.get("confidence", "medium"))
    sources = to_source_chunks(citation_map)

    logger.info(
        "Review complete: %d sources, %d risks, confidence=%s.",
        len(sources), raw.get("risk_count", 0), confidence,
    )

    return {
        "retrieved_sources": sources,
        "context_str": context_str,
        "summary": extract_first_paragraph(markdown),
        "markdown_content": markdown,
        "confidence": confidence,
    }
