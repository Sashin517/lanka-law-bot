"""Quick QA worker node — single-pass RAG pipeline.

Pipeline: Retrieve → Assemble → Generate (hybrid JSON) → Verify citations.

Uses its own LLM chain with the hybrid output format (JSON + markdown).
GenerationService is kept as legacy fallback but no longer used here.
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
from app.agents.prompts.quick_qa_prompt import QUICK_QA_PROMPT
from app.agents.nodes.helpers import (
    extract_first_paragraph,
    normalize_confidence,
    build_and_verify_sources,
    strip_invalid_anchors,
    to_source_chunks,
)
from app.core.config import settings

logger = logging.getLogger(__name__)

# QA LLM chain — hybrid JSON output
_qa_llm = ChatGoogleGenerativeAI(
    model=settings.LLM_MODEL_NAME,
    google_api_key=settings.GOOGLE_API_KEY,
    temperature=settings.LLM_TEMPERATURE,
    max_output_tokens=settings.LLM_MAX_TOKENS,
)
_qa_chain = (
    ChatPromptTemplate.from_template(QUICK_QA_PROMPT)
    | _qa_llm
    | JsonOutputParser()
)


@traceable(name="QuickQANode")
async def quick_qa_node(state: AgentState) -> dict:
    """Execute the single-pass RAG pipeline for fast legal lookups."""

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
            user_doc_results = get_user_doc_retrieval().search(
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
            "summary": "No relevant legal documents were found for this query.",
            "markdown_content": (
                "## No Results Found\n\n"
                "No relevant legal documents were found for this query. "
                "Please try rephrasing your question or using more specific "
                "legal terminology."
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
        "QA context assembled: %d sources, %d chars.",
        len(citation_map), len(context_str),
    )

    # ── Step 4: Generate LLM response (hybrid JSON) ──
    try:
        raw: dict = await _qa_chain.ainvoke({
            "question": state.question,
            "context": context_str,
        })
    except Exception:
        logger.exception("QA LLM generation failed.")
        raw = {
            "answer_markdown": (
                "The AI service is temporarily unavailable. "
                "Please try again shortly."
            ),
            "confidence": "low",
            "sources_used": [],
        }

    # ── Step 5: Verify citations via existing CitationVerifier ──
    markdown = raw.get("answer_markdown", "")
    sources_used = raw.get("sources_used", [])

    # Run verification: strips hallucinated anchors
    valid_ids = build_and_verify_sources(sources_used, citation_map, _verifier)
    markdown = strip_invalid_anchors(markdown, valid_ids)

    confidence = normalize_confidence(raw.get("confidence", "medium"))
    sources = to_source_chunks(citation_map)

    logger.info(
        "QA complete: confidence=%s, sources=%d.",
        confidence, len(sources),
    )

    return {
        "retrieved_sources": sources,
        "context_str": context_str,
        "summary": extract_first_paragraph(markdown),
        "markdown_content": markdown,
        "confidence": confidence,
    }
