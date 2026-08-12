"""Quick QA worker node — single-pass RAG pipeline.

Pipeline: Retrieve → Assemble → Generate (hybrid JSON) → Verify citations.

Uses its own LLM chain with the hybrid output format (JSON + markdown).
GenerationService is kept as legacy fallback but no longer used here.

If the user's question matches a citation-verification pattern
(e.g. "Does Section 12 of the Rent Act say…"), this node internally
delegates to the verify_node for a targeted fact-check pipeline.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from evaluation.ablation import retrieval_search_kwargs
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig
from langchain_google_genai import ChatGoogleGenerativeAI
from langsmith import traceable

from app.agents.message_bus import emit_message, enrich_context_with_upstream
from app.agents.nodes.helpers import (
    build_and_verify_sources,
    enrich_context_with_conversation,
    extract_first_paragraph,
    normalize_confidence,
    strip_invalid_anchors,
    to_source_chunks,
)
from app.agents.nodes.verify_node import verify_node
from app.agents.prompts.quick_qa_prompt import QUICK_QA_PROMPT
from app.agents.shared import (
    citation_verifier as _verifier,
)
from app.agents.shared import (
    context_assembler as _assembler,
)
from app.agents.shared import (
    get_user_doc_retrieval,
)
from app.agents.shared import (
    retrieval_service as _retrieval,
)
from app.agents.state import AgentState
from app.agents.streaming import get_emitter
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
    ChatPromptTemplate.from_template(QUICK_QA_PROMPT) | _qa_llm | JsonOutputParser()
)


@traceable(name="QuickQANode")
async def quick_qa_node(
    state: AgentState,
    config: Optional[RunnableConfig] = None,  # noqa: UP045
) -> dict:
    """Execute the single-pass RAG pipeline for fast legal lookups.

    If the question matches a citation-verification pattern, delegates
    to ``verify_node`` as an internal sub-mode.
    """

    emitter = get_emitter(config)
    emitter.emit_step_start("quick_qa", "Searching legal corpus")

    # ── Sub-mode: verify request detection ──
    if _is_verify_request(state.question):
        logger.info(
            "Verify sub-mode triggered within quick_qa for: '%s'", state.question[:80]
        )
        emitter.emit_step_done(
            "quick_qa",
            "Verification request detected",
            delegated_to="verify",
        )
        return await verify_node(state, config)

    # ── Step 1: Retrieve from legal corpus ──
    legal_results: list[dict] = []
    if state.use_legal_corpus:
        legal_results = _retrieval.search(
            query=state.question,
            top_k=state.legal_top_k,
            year_filter=state.year_filter,
            act_name_filter=state.act_name_filter,
            **retrieval_search_kwargs(state.ablation_config),
        )

    # ── Step 2: Retrieve from user documents (if applicable) ──
    user_doc_results: list[dict] = []
    if state.use_user_documents and state.document_ids:
        emitter.emit_step_detail("quick_qa", "Searching uploaded documents")
        try:
            user_doc_results = get_user_doc_retrieval().search(
                query=state.question,
                document_ids=state.document_ids,
                matter_id=state.matter_id,
                top_k=state.user_doc_top_k,
                expand_parents=state.ablation_config.get("expand_parents", True),
            )
        except Exception:
            logger.exception("User-document retrieval failed in quick_qa_node.")

    # Handle empty retrieval
    if not legal_results and not user_doc_results:
        logger.warning("No retrieval results for: '%s'", state.question[:80])
        emitter.emit_sources_found(0, [])
        emitter.emit_step_done(
            "quick_qa",
            "Search completed with no matching sources",
            source_count=0,
        )
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
        len(citation_map),
        len(context_str),
    )
    emitter.emit_sources_found(
        len(citation_map),
        [source.title for source in citation_map.values()],
    )

    # ── Enrich with upstream agent outputs (when running in a multi-step plan) ──
    context_str = enrich_context_with_upstream(state, context_str, logger)
    llm_context = enrich_context_with_conversation(state, context_str)

    # ── Step 4: Generate LLM response (hybrid JSON) ──
    emitter.emit_step_detail("quick_qa", "Generating answer from retrieved sources")
    question_for_llm = state.question
    grounding_feedback = state.working_memory.get("grounding_feedback")
    if grounding_feedback:
        logger.info("Retrying quick_qa with grounding feedback: %s", grounding_feedback)
        question_for_llm += (
            f"\n\n[RETRY NOTICE: Previous answer contained ungrounded claims: {grounding_feedback}. "
            f"Ensure every statement is strictly backed by the sources below.]"
        )

    try:
        raw: dict = await _qa_chain.ainvoke(
            {
                "question": question_for_llm,
                "context": llm_context,
            }
        )
    except Exception:
        logger.exception("QA LLM generation failed.")
        raw = {
            "answer_markdown": (
                "The AI service is temporarily unavailable. Please try again shortly."
            ),
            "confidence": "low",
            "sources_used": [],
        }

    # ── Step 5: Verify citations via existing CitationVerifier ──
    markdown = raw.get("answer_markdown", "")
    sources_used = raw.get("sources_used", [])

    # Run verification: strips hallucinated anchors
    if not state.ablation_config.get("skip_verification"):
        emitter.emit_step_start("verification", "Verifying citations")
        valid_ids = build_and_verify_sources(
            sources_used, citation_map, _verifier, markdown_content=markdown
        )
        markdown = strip_invalid_anchors(markdown, valid_ids)
        emitter.emit_step_done(
            "verification",
            f"{len(valid_ids)}/{len(citation_map)} source citations verified",
            verified_count=len(valid_ids),
            source_count=len(citation_map),
        )

    confidence = normalize_confidence(raw.get("confidence", "medium"))
    sources = to_source_chunks(citation_map)

    logger.info(
        "QA complete: confidence=%s, sources=%d.",
        confidence,
        len(sources),
    )
    emitter.emit_step_done(
        "quick_qa",
        "Legal answer generated",
        source_count=len(sources),
    )

    return emit_message(
        state=state,
        state_update={
            "retrieved_sources": sources,
            "context_str": context_str,
            "summary": extract_first_paragraph(markdown),
            "markdown_content": markdown,
            "confidence": confidence,
        },
        sender="quick_qa",
        msg_type="qa_answer",
        content=markdown,
    )


# ── Helpers ──────────────────────────────────────────────────────


def _is_verify_request(question: str) -> bool:
    """Detect explicit citation-verification requests.

    Triggers the verify sub-mode for questions like:
    - "Verify that Section 12 of the Rent Act says..."
    - "Is it true that the Penal Code Section 300 states..."
    - "Confirm that tenants cannot be evicted under..."
    """
    text = question.lower()
    return bool(
        re.search(r"\bverify\b.*\b(section|act|clause|case)\b", text)
        or re.search(r"\b(is it true|does .+ say|confirm that)\b", text)
    )
