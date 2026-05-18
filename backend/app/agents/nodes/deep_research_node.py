"""Deep Research worker node — iterative multi-hop legal research.

Pipeline:
  1. Decompose the question into 2-3 focused sub-queries (LLM call)
  2. Retrieve for each sub-query in parallel (asyncio.gather)
  3. Optionally retrieve from user documents when document_ids present
  4. Deduplicate and merge all results via content fingerprinting
  5. Assemble combined context with citation anchors
  6. Synthesize a comprehensive research memo (hybrid JSON + markdown)
  7. Verify citations via existing CitationVerifier
"""

from __future__ import annotations

import asyncio
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
from app.agents.prompts.decomposition_prompt import DECOMPOSITION_PROMPT
from app.agents.prompts.deep_research_prompt import DEEP_RESEARCH_PROMPT
from app.agents.nodes.helpers import (
    extract_first_paragraph,
    normalize_confidence,
    build_and_verify_sources,
    strip_invalid_anchors,
    to_source_chunks,
)
from app.core.config import settings

logger = logging.getLogger(__name__)

# Decomposition LLM — fast model for query splitting
_decomp_llm = ChatGoogleGenerativeAI(
    model=settings.LLM_MODEL_NAME,
    google_api_key=settings.GOOGLE_API_KEY,
    temperature=0.0,
    max_output_tokens=512,
)
_decomp_chain = (
    ChatPromptTemplate.from_template(DECOMPOSITION_PROMPT)
    | _decomp_llm
    | JsonOutputParser()
)

# Synthesis LLM — higher capability model for research memo generation
_synthesis_llm = ChatGoogleGenerativeAI(
    model=settings.LLM_MODEL_NAME,
    google_api_key=settings.GOOGLE_API_KEY,
    temperature=settings.LLM_TEMPERATURE,
    max_output_tokens=settings.LLM_MAX_TOKENS,
)
_synthesis_chain = (
    ChatPromptTemplate.from_template(DEEP_RESEARCH_PROMPT)
    | _synthesis_llm
    | JsonOutputParser()
)


@traceable(name="DeepResearchNode")
async def deep_research_node(state: AgentState) -> dict:
    """Execute the multi-hop research pipeline.

    Decomposes → parallel retrieve → merge → synthesize → verify.
    """

    # ── Step 1: Decompose question into sub-queries ──
    sub_queries = await _decompose_query(state.question)
    logger.info("Decomposed into %d sub-queries: %s", len(sub_queries), sub_queries)

    # ── Step 2: Parallel retrieval across all sub-queries ──
    legal_results = await _parallel_legal_retrieval(sub_queries, state.ablation_config)
    logger.info("Parallel retrieval returned %d total results.", len(legal_results))

    # ── Step 3: User document retrieval (when document_ids present) ──
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
            logger.exception("User-document retrieval failed in deep_research.")

    # Handle empty retrieval
    if not legal_results and not user_doc_results:
        logger.warning("No results for deep research: '%s'", state.question[:80])
        return {
            "summary": "No relevant legal documents were found.",
            "markdown_content": (
                "## No Results Found\n\n"
                "No relevant legal documents were found for this research query. "
                "Please try rephrasing or narrowing the question."
            ),
            "retrieved_sources": [],
            "sub_queries": sub_queries,
            "context_str": "",
            "confidence": "low",
        }

    # ── Step 4: Assemble context with citation anchors ──
    context_str, citation_map = _assembler.assemble(
        legal_results=legal_results,
        user_document_results=user_doc_results,
    )
    logger.info(
        "Research context assembled: %d sources, %d chars.",
        len(citation_map), len(context_str),
    )

    # ── Step 5: Synthesize research memo (hybrid JSON) ──
    sub_query_text = "\n".join(f"- {sq}" for sq in sub_queries)
    try:
        raw: dict = await _synthesis_chain.ainvoke({
            "question": state.question,
            "sub_queries": sub_query_text,
            "context": context_str,
        })
    except Exception:
        logger.exception("Research synthesis LLM call failed.")
        raw = {
            "memo_markdown": (
                "The AI synthesis service is temporarily unavailable. "
                "Please try again shortly."
            ),
            "confidence": "low",
            "sources_used": [],
        }

    # ── Step 6: Verify citations via existing CitationVerifier ──
    markdown = raw.get("memo_markdown", "")
    sources_used = raw.get("sources_used", [])

    if not state.ablation_config.get("skip_verification"):
        valid_ids = build_and_verify_sources(sources_used, citation_map, _verifier)
        markdown = strip_invalid_anchors(markdown, valid_ids)

    confidence = normalize_confidence(raw.get("confidence", "medium"))
    sources = to_source_chunks(citation_map)

    logger.info(
        "Deep research complete: %d sub-queries, %d sources, confidence=%s.",
        len(sub_queries), len(sources), confidence,
    )

    return {
        "retrieved_sources": sources,
        "sub_queries": sub_queries,
        "context_str": context_str,
        "summary": extract_first_paragraph(markdown),
        "markdown_content": markdown,
        "confidence": confidence,
    }


# ── Internal helpers ──────────────────────────────────────────────


async def _decompose_query(question: str) -> list[str]:
    """Use LLM to split a complex question into 2-3 sub-queries."""
    try:
        result = await _decomp_chain.ainvoke({"question": question})
        sub_queries = result.get("sub_queries", [])
        # Validate and cap at 3 sub-queries
        if isinstance(sub_queries, list) and sub_queries:
            return [str(q) for q in sub_queries[:3]]
    except Exception:
        logger.exception("Query decomposition failed; using original question.")

    # Fallback: use the original question as-is
    return [question]


async def _parallel_legal_retrieval(sub_queries: list[str], ablation_config: dict) -> list[dict]:
    """Run retrieval for all sub-queries concurrently, then deduplicate."""
    tasks = [
        asyncio.to_thread(
            _retrieval.search,
            query=sq,
            top_k=5,
            expand_parents=ablation_config.get("expand_parents", True),
            **ablation_config,
        )
        for sq in sub_queries
    ]
    batches = await asyncio.gather(*tasks, return_exceptions=True)

    # Flatten results, skipping any failed batches
    all_results: list[dict] = []
    for i, batch in enumerate(batches):
        if isinstance(batch, Exception):
            logger.warning("Sub-query %d retrieval failed: %s", i, batch)
            continue
        all_results.extend(batch)

    return _deduplicate_results(all_results)


def _deduplicate_results(results: list[dict]) -> list[dict]:
    """Remove duplicate retrieval results by content fingerprint."""
    seen: set[str] = set()
    unique: list[dict] = []
    for result in results:
        child = result.get("child")
        if child is None:
            continue
        # Use first 500 chars as fingerprint
        key = child.page_content[:500].strip()
        if key in seen:
            continue
        seen.add(key)
        unique.append(result)
    return unique
