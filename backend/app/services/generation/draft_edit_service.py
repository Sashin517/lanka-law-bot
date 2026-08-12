"""Application service for targeted and structural legal-draft edits."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from evaluation.ablation import retrieval_search_kwargs
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

from app.agents.nodes.helpers import (
    build_and_verify_sources,
    normalize_anchor,
    normalize_confidence,
    strip_invalid_anchors,
)
from app.agents.prompts.draft_edit_prompt import DRAFT_EDIT_PROMPT
from app.agents.runtime import get_graph
from app.agents.state import AgentState
from app.agents.streaming import FinalSuppressingEmitter, IStreamEmitter, NullEmitter
from app.core.config import settings
from app.schemas.requests import DraftEditRequest
from app.schemas.responses import DraftEditResponse, SourceReference

logger = logging.getLogger(__name__)


class DraftEditError(RuntimeError):
    """Raised when an edit cannot be produced or safely applied."""


class DraftEditConflictError(DraftEditError):
    """Raised when the editor selection is stale or ambiguous."""


@lru_cache(maxsize=1)
def _get_edit_chain() -> Any:
    """Construct the single-call light edit chain once per process."""

    llm = ChatGoogleGenerativeAI(
        model=settings.LLM_MODEL_NAME,
        google_api_key=settings.GOOGLE_API_KEY,
        temperature=settings.LLM_TEMPERATURE,
        max_output_tokens=settings.LLM_MAX_TOKENS,
    )
    prompt = ChatPromptTemplate.from_template(DRAFT_EDIT_PROMPT)
    return prompt | llm | JsonOutputParser()


@lru_cache(maxsize=1)
def _get_light_dependencies() -> tuple[Any, Any, Any]:
    """Resolve shared retrieval dependencies only when a light edit runs."""

    from app.agents.shared import (
        citation_verifier,
        context_assembler,
        retrieval_service,
    )

    return retrieval_service, context_assembler, citation_verifier


async def process_light_edit(
    request: DraftEditRequest,
    *,
    stream_emitter: IStreamEmitter | None = None,
) -> DraftEditResponse:
    """Apply a localized edit using retrieval and one structured LLM call."""

    emitter = stream_emitter if stream_emitter is not None else NullEmitter()
    retrieval, assembler, verifier = _get_light_dependencies()
    emitter.emit_step_detail("edit", "Retrieving relevant legal authorities")
    try:
        legal_results = retrieval.search(
            query=request.instruction,
            top_k=5,
            **retrieval_search_kwargs({}),
        )
        context, citation_map = assembler.assemble(
            legal_results=legal_results,
            user_document_results=[],
        )
        emitter.emit_sources_found(
            len(citation_map),
            [source.title for source in citation_map.values()],
        )
    except Exception as exc:
        logger.exception(
            "Legal context retrieval failed for draft %s.",
            request.draft_id,
        )
        raise DraftEditError("Legal context retrieval for the edit failed.") from exc

    emitter.emit_step_detail("edit", "Generating the targeted revision")
    try:
        raw = await _get_edit_chain().ainvoke(
            {
                "current_content": request.current_content,
                "selected_text": request.selected_text or "(No text selected)",
                "instruction": request.instruction,
                "context": context or "(No legal context was retrieved.)",
            }
        )
    except Exception as exc:
        logger.exception(
            "Targeted draft edit generation failed for draft %s.",
            request.draft_id,
        )
        raise DraftEditError("The targeted edit could not be generated.") from exc

    if not isinstance(raw, dict):
        raise DraftEditError(
            "The targeted edit returned an invalid structured response."
        )

    edited_text = raw.get("edited_text")
    if not isinstance(edited_text, str) or not edited_text.strip():
        raise DraftEditError("The targeted edit returned no replacement text.")

    sources_used = raw.get("sources_used", [])
    if not isinstance(sources_used, list):
        sources_used = []
    emitter.emit_step_detail("edit", "Verifying citations in the revision")
    try:
        valid_ids = build_and_verify_sources(
            sources_used,
            citation_map,
            verifier,
            markdown_content=edited_text,
        )
        edited_text = strip_invalid_anchors(edited_text.strip(), valid_ids)
    except Exception as exc:
        logger.exception(
            "Citation verification failed for draft %s.",
            request.draft_id,
        )
        raise DraftEditError("Citation verification for the edit failed.") from exc
    if not edited_text:
        raise DraftEditError("The targeted edit contained no verified content.")

    # The server derives operation semantics from the request instead of
    # trusting an inconsistent model-provided edit_type.
    edit_type = "replace" if request.selected_text else "insert"
    markdown_content = _apply_local_edit(request, edited_text)

    return DraftEditResponse(
        edit_type=edit_type,
        original_text=request.selected_text or "",
        edited_text=edited_text,
        markdown_content=markdown_content,
        sources=_referenced_sources(citation_map, valid_ids),
        edit_summary=_safe_summary(raw.get("edit_summary"), request.instruction),
        confidence=normalize_confidence(str(raw.get("confidence", "medium"))),
        edit_path="light",
    )


async def process_heavy_edit(
    request: DraftEditRequest,
    *,
    stream_emitter: IStreamEmitter | None = None,
) -> DraftEditResponse:
    """Run a structural revision through the existing multi-agent graph."""

    excerpt = request.current_content[:3_000]
    if len(request.current_content) > len(excerpt):
        excerpt += "..."
    question = (
        "REVISION REQUEST: The user has an existing legal draft and wants "
        "the following changes:\n\n"
        f"## Edit Instruction:\n{request.instruction}\n\n"
        "## Existing Draft (to be revised):\n"
        f"{excerpt}"
    )
    initial_state = AgentState(
        question=question,
        mode="drafting",
        document_ids=request.document_ids,
        working_memory={
            "existing_draft": request.current_content,
            "revision_instruction": request.instruction,
            "selected_text": request.selected_text,
            "is_revision": True,
        },
    )

    try:
        if stream_emitter is None:
            # Preserve the legacy invocation exactly for non-streaming callers.
            final_state = await get_graph().ainvoke(initial_state.model_dump())
        else:
            # The child graph's formatter emits a LegalQueryResponse-shaped
            # final. Suppress only that event; the endpoint emits the adapted
            # DraftEditResponse as the stream's single authoritative final.
            child_emitter = FinalSuppressingEmitter(stream_emitter)
            final_state = await get_graph().ainvoke(
                initial_state.model_dump(),
                config={"configurable": {"stream_emitter": child_emitter}},
            )
    except Exception as exc:
        logger.exception(
            "Structural draft revision failed for draft %s.",
            request.draft_id,
        )
        raise DraftEditError("The structural revision pipeline failed.") from exc

    if not isinstance(final_state, dict):
        raise DraftEditError("The structural revision pipeline returned invalid state.")
    final = final_state.get("final_response") or {}
    if not isinstance(final, dict):
        raise DraftEditError(
            "The structural revision pipeline returned invalid output."
        )
    markdown = final.get("markdown_content")
    if not isinstance(markdown, str) or not markdown.strip():
        raise DraftEditError("The structural revision pipeline returned no document.")

    return DraftEditResponse(
        edit_type="full_rewrite",
        original_text=request.current_content,
        edited_text=markdown,
        markdown_content=markdown,
        sources=_coerce_sources(final.get("sources")),
        edit_summary=(
            final.get("change_summary") or f"Full revision: {request.instruction[:100]}"
        ),
        confidence=normalize_confidence(str(final.get("confidence", "medium"))),
        edit_path="heavy",
        execution_trace=(
            final.get("execution_trace")
            if isinstance(final.get("execution_trace"), dict)
            else None
        ),
    )


def _apply_local_edit(
    request: DraftEditRequest,
    edited_text: str,
) -> str:
    """Merge replacement text without trusting editor offsets blindly.

    Tiptap positions are ProseMirror positions, not guaranteed Markdown string
    offsets. An offset is therefore used only when it identifies the exact
    selected text; otherwise an unambiguous text match is required.
    """

    content = request.current_content
    selected = request.selected_text
    if not selected:
        separator = "\n\n" if content and not content.endswith("\n\n") else ""
        return f"{content}{separator}{edited_text}"

    start = request.selection_start
    end = request.selection_end
    if (
        start is not None
        and end is not None
        and end <= len(content)
        and content[start:end] == selected
    ):
        return f"{content[:start]}{edited_text}{content[end:]}"

    first = content.find(selected)
    if first < 0:
        raise DraftEditConflictError(
            "The selected text no longer exists in the current draft."
        )
    if content.find(selected, first + len(selected)) >= 0:
        raise DraftEditConflictError(
            "The selected text occurs more than once; refresh the selection and retry."
        )
    return f"{content[:first]}{edited_text}{content[first + len(selected) :]}"


def _referenced_sources(
    citation_map: dict[str, SourceReference],
    valid_ids: set[str],
) -> list[SourceReference]:
    normalized_valid = {normalize_anchor(value) for value in valid_ids}
    return [
        source
        for citation_id, source in citation_map.items()
        if normalize_anchor(citation_id) in normalized_valid
    ]


def _coerce_sources(value: Any) -> list[SourceReference]:
    if not isinstance(value, list):
        return []
    sources: list[SourceReference] = []
    for item in value:
        try:
            sources.append(
                item
                if isinstance(item, SourceReference)
                else SourceReference.model_validate(item)
            )
        except (TypeError, ValueError):
            logger.warning("Ignoring malformed source in structural edit response.")
    return sources


def _safe_summary(value: Any, instruction: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()[:1_000]
    return f"Applied targeted edit: {instruction[:200]}"
