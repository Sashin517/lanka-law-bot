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
from app.agents.prompts.reasoning_prompt import REASONING_PROMPT
from app.agents.nodes.helpers import (
    extract_first_paragraph,
    normalize_confidence,
    build_and_verify_sources,
    strip_invalid_anchors,
    to_source_chunks,
)
from app.core.config import settings

logger = logging.getLogger(__name__)

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


@traceable(name="ReasoningNode")
async def reasoning_node(state: AgentState) -> dict:
    """Execute the IRAC legal analysis pipeline.

    Uses expanded retrieval (top_k=8) to gather broader context,
    then generates structured Issue-Rule-Application-Conclusion markdown.
    """

    # ── Step 1: Expanded retrieval from legal corpus ──
    legal_results: list[dict] = []
    if state.use_legal_corpus:
        legal_results = _retrieval.search(
            query=state.question,
            top_k=_REASONING_TOP_K,
            expand_parents=state.ablation_config.get("expand_parents", True),
            **state.ablation_config,
            # No entity filters — reasoning needs broad context
        )

    # ── Step 2: User document retrieval (if applicable) ──
    user_doc_results: list[dict] = []
    if state.use_user_documents and state.document_ids:
        try:
            user_doc_results = get_user_doc_retrieval().search(
                query=state.question,
                document_ids=state.document_ids,
                matter_id=state.matter_id,
                top_k=state.user_doc_top_k,
                expand_parents=state.ablation_config.get("expand_parents", True),
            )
        except Exception:
            logger.exception("User-document retrieval failed in reasoning_node.")

    # Handle empty retrieval
    if not legal_results and not user_doc_results:
        logger.warning("No retrieval results for reasoning: '%s'", state.question[:80])
        return {
            "summary": "No relevant legal documents were found.",
            "markdown_content": (
                "## No Results Found\n\n"
                "No relevant legal documents were found to perform this "
                "analysis. Please try rephrasing your question or using "
                "more specific legal terminology."
            ),
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

    # ── Step 4: Generate IRAC analysis (hybrid JSON) ──
    try:
        raw: dict = await _reasoning_chain.ainvoke({
            "question": state.question,
            "context": context_str,
        })
    except Exception:
        logger.exception("Reasoning LLM generation failed.")
        raw = {
            "analysis_markdown": (
                "The AI analysis service is temporarily unavailable. "
                "Please try again shortly."
            ),
            "confidence": "low",
            "sources_used": [],
        }

    # ── Step 5: Verify citations via existing CitationVerifier ──
    markdown = raw.get("analysis_markdown", "")
    sources_used = raw.get("sources_used", [])

    if not state.ablation_config.get("skip_verification"):
        valid_ids = build_and_verify_sources(sources_used, citation_map, _verifier)
        markdown = strip_invalid_anchors(markdown, valid_ids)

    confidence = normalize_confidence(raw.get("confidence", "medium"))
    sources = to_source_chunks(citation_map)

    logger.info(
        "Reasoning complete: %d sources, confidence=%s.",
        len(sources), confidence,
    )

    return {
        "retrieved_sources": sources,
        "context_str": context_str,
        "summary": extract_first_paragraph(markdown),
        "markdown_content": markdown,
        "confidence": confidence,
    }
