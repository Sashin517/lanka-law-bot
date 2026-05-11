"""Deep Research worker node — iterative multi-hop legal research.

Pipeline:
  1. Decompose the question into 2-3 focused sub-queries (LLM call)
  2. Retrieve for each sub-query in parallel (asyncio.gather)
  3. Optionally retrieve from user documents when document_ids present
  4. Deduplicate and merge all results via content fingerprinting
  5. Assemble combined context with citation anchors
  6. Synthesize a comprehensive research memo (LLM call)
  7. Verify citations (strip hallucinated IDs)
"""

from __future__ import annotations

import asyncio
import logging
from functools import lru_cache

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langsmith import traceable

from app.agents.state import AgentState, CitedClaim, SourceChunk
from app.agents.prompts.decomposition_prompt import DECOMPOSITION_PROMPT
from app.agents.prompts.deep_research_prompt import DEEP_RESEARCH_PROMPT
from app.core.config import settings
from app.schemas.responses import LegalResponse, SourceReference, CitedClaim as SchemaCitedClaim, ConfidenceLevel
from app.services.retrieval_service import RetrievalService
from app.services.context_assembler import MultiSourceContextAssembler
from app.services.citation_verifier import CitationVerifier
from app.services.user_document_retrieval_service import UserDocumentRetrievalService

logger = logging.getLogger(__name__)

# Shared singletons
_retrieval = RetrievalService()
_assembler = MultiSourceContextAssembler()
_verifier = CitationVerifier()

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


@lru_cache(maxsize=1)
def _user_doc_retrieval() -> UserDocumentRetrievalService:
    """Lazy-load user-document retrieval (only when needed)."""
    return UserDocumentRetrievalService()


@traceable(name="DeepResearchNode")
async def deep_research_node(state: AgentState) -> dict:
    """Execute the multi-hop research pipeline.

    Decomposes → parallel retrieve → merge → synthesize → verify.
    """

    # ── Step 1: Decompose question into sub-queries ──
    sub_queries = await _decompose_query(state.question)
    logger.info("Decomposed into %d sub-queries: %s", len(sub_queries), sub_queries)

    # ── Step 2: Parallel retrieval across all sub-queries ──
    legal_results = await _parallel_legal_retrieval(sub_queries)
    logger.info("Parallel retrieval returned %d total results.", len(legal_results))

    # ── Step 3: User document retrieval (when document_ids present) ──
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
            logger.exception("User-document retrieval failed in deep_research.")

    # Handle empty retrieval
    if not legal_results and not user_doc_results:
        logger.warning("No results for deep research: '%s'", state.question[:80])
        return {
            "summary": (
                "No relevant legal documents were found for this research query. "
                "Please try rephrasing or narrowing the question."
            ),
            "analysis": [],
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

    # ── Step 5: Synthesize research memo ──
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
            "summary": (
                "The AI synthesis service is temporarily unavailable. "
                "Below are the most relevant source excerpts."
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

    logger.info(
        "Deep research complete: %d sub-queries, %d sources, %d claims.",
        len(sub_queries), len(sources), len(analysis),
    )

    return {
        "retrieved_sources": sources,
        "sub_queries": sub_queries,
        "context_str": context_str,
        "summary": response.summary,
        "analysis": analysis,
        "confidence": response.confidence
        if isinstance(response.confidence, str)
        else response.confidence.value,
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


async def _parallel_legal_retrieval(sub_queries: list[str]) -> list[dict]:
    """Run retrieval for all sub-queries concurrently, then deduplicate."""
    tasks = [
        asyncio.to_thread(
            _retrieval.search,
            query=sq,
            top_k=5,
            expand_parents=True,
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
