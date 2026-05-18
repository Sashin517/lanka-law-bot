"""Verify worker node — citation fact-checker.

Pipeline:
  1. Parse the user's claim to identify the act/section being cited
  2. Targeted retrieval using act_name_filter for precision
  3. Assemble context with citation anchors
  4. Compare claim against actual retrieved source text
  5. Generate verification report: CONFIRMED / PARTIALLY CORRECT / UNCONFIRMED
  6. Verify citations

This agent is user-triggered only — activated when the user explicitly
asks to verify a legal citation (e.g. "Does Section 12 of the Rent Act
say that tenants cannot be evicted?").
"""

from __future__ import annotations

import logging
import re

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langsmith import traceable

from app.agents.state import AgentState
from app.agents.shared import (
    retrieval_service as _retrieval,
    context_assembler as _assembler,
    citation_verifier as _verifier,
)
from app.agents.prompts.verify_prompt import VERIFY_PROMPT
from app.agents.nodes.helpers import (
    extract_first_paragraph,
    normalize_confidence,
    build_and_verify_sources,
    strip_invalid_anchors,
    to_source_chunks,
)
from app.core.config import settings

logger = logging.getLogger(__name__)

# Verify LLM — deterministic for fact-checking
_verify_llm = ChatGoogleGenerativeAI(
    model=settings.LLM_MODEL_NAME,
    google_api_key=settings.GOOGLE_API_KEY,
    temperature=0.0,  # Deterministic for fact-checking
    max_output_tokens=settings.LLM_MAX_TOKENS,
)
_verify_chain = (
    ChatPromptTemplate.from_template(VERIFY_PROMPT) | _verify_llm | JsonOutputParser()
)


@traceable(name="VerifyNode")
async def verify_node(state: AgentState) -> dict:
    """Execute the citation verification pipeline.

    Parses the user's claim → targeted retrieval → comparison → verdict.
    """

    # ── Step 1: Extract verification target from the question ──
    act_name, section_ref = _extract_citation_target(state.question)
    logger.info(
        "Verify target: act='%s', section='%s'",
        act_name or "(none)",
        section_ref or "(none)",
    )

    # ── Step 2: Targeted retrieval — narrow search for the cited provision ──
    search_query = state.question
    if act_name and section_ref:
        search_query = f"{section_ref} {act_name}"
    elif act_name:
        search_query = f"{act_name} {state.question}"

    legal_results = _retrieval.search(
        query=search_query,
        top_k=5,
        expand_parents=state.ablation_config.get("expand_parents", True),
        act_name_filter=act_name,  # Narrow to specific act when detected
        **state.ablation_config,
    )

    # Handle empty retrieval
    if not legal_results:
        logger.warning("No results for verification: '%s'", state.question[:80])
        return {
            "summary": "UNCONFIRMED — The cited provision could not be found.",
            "markdown_content": (
                "## Verification Report\n\n"
                "❌ **UNCONFIRMED** — The cited provision could not be found "
                "in the available legal database. The citation may refer "
                "to a source not yet indexed."
            ),
            "retrieved_sources": [],
            "context_str": "",
            "confidence": "low",
        }

    # ── Step 3: Assemble context with citation anchors ──
    context_str, citation_map = _assembler.assemble(
        legal_results=legal_results,
        user_document_results=[],
    )
    logger.info(
        "Verify context assembled: %d sources, %d chars.",
        len(citation_map), len(context_str),
    )

    # ── Step 4: Compare claim against sources (hybrid JSON) ──
    try:
        raw: dict = await _verify_chain.ainvoke({
            "question": state.question,
            "context": context_str,
        })
    except Exception:
        logger.exception("Verify LLM generation failed.")
        raw = {
            "verdict_markdown": (
                "The verification service is temporarily unavailable. "
                "Please try again shortly."
            ),
            "confidence": "low",
            "sources_used": [],
            "verdict": "UNCONFIRMED",
        }

    # ── Step 5: Verify citations via existing CitationVerifier ──
    markdown = raw.get("verdict_markdown", "")
    sources_used = raw.get("sources_used", [])

    if not state.ablation_config.get("skip_verification"):
        valid_ids = build_and_verify_sources(sources_used, citation_map, _verifier)
        markdown = strip_invalid_anchors(markdown, valid_ids)

    confidence = normalize_confidence(raw.get("confidence", "medium"))
    sources = to_source_chunks(citation_map)

    logger.info(
        "Verification complete: %d sources, verdict=%s.",
        len(sources), raw.get("verdict", "unknown"),
    )

    return {
        "retrieved_sources": sources,
        "context_str": context_str,
        "summary": extract_first_paragraph(markdown),
        "markdown_content": markdown,
        "confidence": confidence,
    }


# ── Helpers ───────────────────────────────────────────────────────


def _extract_citation_target(question: str) -> tuple[str | None, str | None]:
    """Extract the act name and section reference from a verification query.

    Examples:
      "Does Section 12 of the Rent Act say..." → ("Rent Act", "Section 12")
      "Verify that the Penal Code Section 300 states..." → ("Penal Code", "Section 300")
    """
    text = question

    # Pattern: "Section X of the [Act Name]"
    match = re.search(
        r"(section\s+\d+[a-zA-Z]?)\s+of\s+(?:the\s+)?(.+?)(?:\s+(?:says?|states?|provides?|mentions?)|\s*$)",
        text, re.IGNORECASE,
    )
    if match:
        return match.group(2).strip().rstrip(".,"), match.group(1).strip()

    # Pattern: "[Act Name] Section X"
    match = re.search(
        r"(?:the\s+)?(.+?)\s+(section\s+\d+[a-zA-Z]?)",
        text, re.IGNORECASE,
    )
    if match:
        candidate = match.group(1).strip()
        # Filter out common false positives
        if len(candidate.split()) <= 6 and candidate.lower() not in {
            "does", "verify", "confirm", "is", "check",
        }:
            return candidate.rstrip(".,"), match.group(2).strip()

    # Pattern: just an act name without section
    act_patterns = [
        r"(?:the\s+)?([\w\s]+(?:Act|Ordinance|Code|Law))\s+(?:No\.\s*\d+)?",
    ]
    for pattern in act_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip(), None

    return None, None
