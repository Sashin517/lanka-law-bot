"""Service for mode-aware prompt rewriting via LLM."""

from __future__ import annotations
import re

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langsmith import traceable

from app.core.config import settings
from app.schemas.requests import QueryMode
from app.schemas.responses import ImprovePromptResponse
from app.services.generation.prompt_improvement_prompt import (
    MODE_GUIDANCE,
    PROMPT_IMPROVEMENT_TEMPLATE,
)

_improve_llm = ChatGoogleGenerativeAI(
    model=settings.LLM_MODEL_NAME,
    google_api_key=settings.GOOGLE_API_KEY,
    temperature=settings.PROMPT_IMPROVE_TEMPERATURE,
    max_output_tokens=768,
)
_improve_chain = (
    ChatPromptTemplate.from_template(PROMPT_IMPROVEMENT_TEMPLATE)
    | _improve_llm
    | JsonOutputParser()
)


def _looks_truncated(text: str) -> bool:
    """Heuristic guard for obviously cut-off generations."""
    cleaned = text.strip()
    if len(cleaned) < 24:
        return True
    if re.search(r"\bof\s+\d{1,3}$", cleaned, flags=re.IGNORECASE):
        return True
    return cleaned[-1] not in {".", "!", "?", '"', "'", ")"}


def _looks_overcompressed(draft: str, improved_prompt: str) -> bool:
    """Detect rewrites that likely discarded a useful fact pattern."""
    draft_clean = draft.strip()
    improved_clean = improved_prompt.strip()
    if len(draft_clean) < 280:
        return False
    if len(improved_clean) >= int(len(draft_clean) * 0.72):
        return False

    fact_pattern_markers = (
        " agrees ",
        " pays ",
        " refuses ",
        " wishes ",
        " month ",
        " witnesses",
        " property",
        " contract",
        " advance",
    )
    return sum(marker in draft_clean.lower() for marker in fact_pattern_markers) >= 3


def _fact_preserving_fallback(draft: str) -> str:
    """Return a safe prompt that preserves all user facts if rewriting fails."""
    return (
        f"Facts: {draft.strip()}\n\n"
        "Question: Based on these facts and Sri Lankan law, identify the legal "
        "hurdles, applicable formal requirements, and available remedies relevant "
        "to the user's requested issue."
    )


class PromptImprovementService:
    """Rewrites user prompts with mode-aware instruction quality."""

    @traceable(name="PromptImprovementService")
    async def improve(
        self,
        draft: str,
        mode: QueryMode,
        has_documents: bool,
    ) -> ImprovePromptResponse:
        mode_value = mode.value
        payload = {
            "draft": draft,
            "mode": mode_value,
            "has_documents": "yes" if has_documents else "no",
            "mode_guidance": MODE_GUIDANCE.get(mode_value, MODE_GUIDANCE["quick_qa"]),
        }

        raw: dict = await _improve_chain.ainvoke(payload)

        improved_prompt = str(raw.get("improved_prompt", "")).strip()
        if (
            not improved_prompt
            or _looks_truncated(improved_prompt)
            or _looks_overcompressed(draft, improved_prompt)
        ):
            # Retry once with an explicit continuation-safe instruction.
            retry_payload = {
                **payload,
                "draft": (
                    f"{draft}\n\n"
                    "Important: Return a complete final prompt. Do not truncate "
                    "mid-sentence, do not compress away material facts, and do "
                    "not add remedies or issues the user did not ask about."
                ),
            }
            raw = await _improve_chain.ainvoke(retry_payload)
            improved_prompt = str(raw.get("improved_prompt", "")).strip()

        if not improved_prompt or _looks_truncated(improved_prompt):
            raise ValueError("LLM returned empty improved_prompt")
        if _looks_overcompressed(draft, improved_prompt):
            improved_prompt = _fact_preserving_fallback(draft)

        intent_summary_raw = raw.get("intent_summary")
        intent_summary = (
            str(intent_summary_raw).strip() if isinstance(intent_summary_raw, str) else None
        )

        return ImprovePromptResponse(
            improved_prompt=improved_prompt,
            intent_summary=intent_summary or None,
        )
