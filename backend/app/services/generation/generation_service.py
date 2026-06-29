from __future__ import annotations

import json
import logging
from langchain_openai import ChatOpenAI
from langsmith import traceable
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from app.core.config import settings
from app.schemas.responses import (
    CitedClaim,
    ConfidenceLevel,
    LegalResponse,
    SourceReference,
)
from app.agents.prompts.legal_rag import LEGAL_RAG_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class GenerationService:

    def __init__(self) -> None:
        logger.info(
            "Initialising GenerationService (model=%s) …", settings.LLM_MODEL_NAME
        )

        self._llm = ChatOpenAI(
            model_name=settings.LLM_MODEL_NAME,
            openai_api_key=settings.OPENROUTER_API_KEY,
            openai_api_base="https://openrouter.ai/api/v1",
            temperature=settings.PROMPT_IMPROVE_TEMPERATURE,
            max_tokens=settings.LLM_MAX_TOKENS,
            model_kwargs={
                "extra_headers": {
                    "HTTP-Referer": "https://lankalawbot.com", 
                    "X-Title": "LankaLawBot",
                }
            }
        )
        self._parser = JsonOutputParser()
        self._prompt = ChatPromptTemplate.from_template(LEGAL_RAG_SYSTEM_PROMPT)
        self._chain = self._prompt | self._llm | self._parser

        logger.info("GenerationService ready.")

    @traceable(name="LLM_Generation")
    async def generate(
        self,
        question: str,
        context: str,
        citation_map: dict[str, SourceReference],
    ) -> LegalResponse:

        try:
            raw: dict = await self._chain.ainvoke(
                {
                    "question": question,
                    "context": context,
                }
            )

            # Parse the LLM's JSON output into our response model
            analysis_items: list[CitedClaim] = []
            for item in raw.get("analysis", []):
                if isinstance(item, dict):
                    analysis_items.append(
                        CitedClaim(
                            statement=item.get("statement", ""),
                            citation_ids=item.get("citation_ids", []),
                        )
                    )

            confidence = raw.get("confidence", "medium")
            if confidence not in {e.value for e in ConfidenceLevel}:
                confidence = ConfidenceLevel.MEDIUM

            return LegalResponse(
                summary=raw.get("summary", ""),
                analysis=analysis_items,
                sources=list(citation_map.values()),
                confidence=confidence,
            )

        except Exception as exc:
            logger.exception("LLM generation failed: %s", exc)
            return self._fallback(question, citation_map, str(exc))

    def _fallback(
        self,
        question: str,
        citation_map: dict[str, SourceReference],
        error: str,
    ) -> LegalResponse:

        logger.warning("Using fallback response for query: '%s'", question[:80])

        # Build analysis entries from the raw sources
        fallback_analysis: list[CitedClaim] = []
        for anchor, source in citation_map.items():
            fallback_analysis.append(
                CitedClaim(
                    statement=f"[Source excerpt] {source.excerpt}…",
                    citation_ids=[anchor],
                )
            )

        return LegalResponse(
            summary=(
                "The AI generation service is temporarily unavailable. "
                "Below are the most relevant source excerpts retrieved "
                "from the Sri Lankan legal database."
            ),
            analysis=fallback_analysis,
            sources=list(citation_map.values()),
            confidence=ConfidenceLevel.LOW,
        )
