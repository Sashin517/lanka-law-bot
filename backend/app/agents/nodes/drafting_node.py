"""Drafting worker node — template-aware legal document generator.

Pipeline:
  1. Select template based on answer_mode / document type detection
  2. Retrieve relevant statutes from legal corpus
  3. Optionally retrieve user document context when document_ids present
  4. Assemble dual-source context with [LAW-*] and [DOC-*] anchors
  5. Generate draft using template-injected prompt (hybrid JSON + markdown)
  6. Verify citations via existing CitationVerifier
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
from app.agents.prompts.drafting_prompt import DRAFTING_PROMPT
from app.agents.templates import TEMPLATE_REGISTRY
from app.agents.nodes.helpers import (
    extract_first_paragraph,
    normalize_confidence,
    build_and_verify_sources,
    strip_invalid_anchors,
    to_source_chunks,
)
from app.core.config import settings

logger = logging.getLogger(__name__)

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
            expand_parents=state.ablation_config.get("expand_parents", True),
            **state.ablation_config,
        )

    # ── Step 3: Retrieve from user documents (if applicable) ──
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
            logger.exception("User-document retrieval failed in drafting_node.")

    # Drafting can proceed with template even without retrieval results
    if not legal_results and not user_doc_results:
        logger.warning("No retrieval results for drafting: '%s'", state.question[:80])

    # ── Step 4: Assemble context with citation anchors ──
    context_str, citation_map = _assembler.assemble(
        legal_results=legal_results,
        user_document_results=user_doc_results,
    )
    logger.info(
        "Drafting context assembled: %d sources, %d chars.",
        len(citation_map), len(context_str),
    )

    # ── Step 5: Generate draft with template-injected prompt (hybrid JSON) ──
    prompt = ChatPromptTemplate.from_template(DRAFTING_PROMPT)
    chain = prompt | _drafting_llm | _drafting_parser

    try:
        raw: dict = await chain.ainvoke({
            "question": state.question,
            "template": template_text,
            "context": context_str
            or "(No source documents available — use template structure only.)",
        })
    except Exception:
        logger.exception("Drafting LLM generation failed.")
        raw = {
            "draft_markdown": (
                "The AI drafting service is temporarily unavailable. "
                "Please try again shortly."
            ),
            "confidence": "low",
            "sources_used": [],
            "requires_completion": True,
        }

    # ── Step 6: Verify citations via existing CitationVerifier ──
    markdown = raw.get("draft_markdown", "")
    sources_used = raw.get("sources_used", [])
    title = raw.get("title") or _extract_title(markdown) or _title_from_template(template_key)
    document_type = raw.get("document_type") or template_key
    requires_completion = bool(raw.get("requires_completion", False))
    section_map = raw.get("section_map") or _build_section_map(markdown)
    change_summary = raw.get("change_summary") or f"Generated {title}."

    if not state.ablation_config.get("skip_verification"):
        valid_ids = build_and_verify_sources(sources_used, citation_map, _verifier)
        markdown = strip_invalid_anchors(markdown, valid_ids)

    confidence = normalize_confidence(raw.get("confidence", "medium"))
    sources = to_source_chunks(citation_map)

    logger.info(
        "Drafting complete: template=%s, %d sources, confidence=%s.",
        template_key, len(sources), confidence,
    )

    return {
        "retrieved_sources": sources,
        "context_str": context_str,
        "summary": extract_first_paragraph(markdown),
        "markdown_content": markdown,
        "draft_content": markdown,          # Backward compat
        "draft_title": title,
        "draft_document_type": document_type,
        "sources_used": sources_used,
        "requires_completion": requires_completion,
        "section_map": section_map,
        "change_summary": change_summary,
        "draft_documents": [
            {
                "title": title,
                "document_type": document_type,
                "draft_markdown": markdown,
                "sources_used": sources_used,
                "requires_completion": requires_completion,
                "section_map": section_map,
                "change_summary": change_summary,
            }
        ],
        "confidence": confidence,
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


def _extract_title(markdown: str) -> str:
    for line in markdown.splitlines():
        text = line.strip()
        if text.startswith("# "):
            return text[2:].strip()
    return ""


def _title_from_template(template_key: str) -> str:
    return {
        "contract": "Generated Contract",
        "pleading": "Generated Pleading",
        "notice": "Generated Notice",
        "affidavit": "Generated Affidavit",
    }.get(template_key, "Generated Legal Draft")


def _build_section_map(markdown: str) -> dict:
    section_map: dict[str, dict] = {}
    for index, line in enumerate(markdown.splitlines(), start=1):
        text = line.strip()
        if not text.startswith("#"):
            continue
        marker, _, heading = text.partition(" ")
        if not heading:
            continue
        section_id = "".join(ch.lower() if ch.isalnum() else "-" for ch in heading).strip("-")
        section_map[section_id or f"section-{index}"] = {
            "heading": heading.strip(),
            "level": len(marker),
            "line": index,
        }
    return section_map
