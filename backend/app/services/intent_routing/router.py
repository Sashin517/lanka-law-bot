from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.output_parsers import JsonOutputParser

from app.core.config import settings
from app.services.intent_routing.fallback import build_fallback_route_plan
from app.services.intent_routing.models import IntentRoutePlan, RouterResult
from app.services.intent_routing.normalizer import normalize_query
from app.services.intent_routing.prompts import INTENT_ROUTER_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class SemanticIntentRouter:
    """LLM-first legal query router with deterministic fallback."""

    def __init__(self, llm: Any | None = None, enable_llm: bool | None = None) -> None:
        self._enable_llm = (
            settings.ROUTER_ENABLE_LLM if enable_llm is None else enable_llm
        )
        self._llm = llm

    async def classify(self, question: str) -> RouterResult:
        normalized = normalize_query(question)
        if not self._enable_llm:
            return RouterResult(
                plan=build_fallback_route_plan(
                    question,
                    "Router LLM disabled; deterministic fallback used.",
                ),
                source="fallback_rules",
            )

        try:
            llm = self._llm or self._build_llm()
            prompt = INTENT_ROUTER_SYSTEM_PROMPT.replace("{{USER_QUERY}}", normalized)
            message = await llm.ainvoke(prompt)
            raw_text = self._message_text(message)
            raw_json = self._parse_json(raw_text)
            raw_json["raw_query"] = question
            raw_json.setdefault("normalized_query", normalized)
            plan = IntentRoutePlan.model_validate(raw_json)
            return RouterResult(plan=plan, source="llm", raw_llm_output=raw_json)
        except Exception as exc:
            logger.warning("Intent router failed; falling back to rules: %s", exc)
            return RouterResult(
                plan=build_fallback_route_plan(
                    question,
                    f"Router failed; deterministic fallback used: {exc}",
                ),
                source="fallback_rules",
                parse_error=str(exc),
            )

    def _build_llm(self) -> ChatGoogleGenerativeAI:
        return ChatGoogleGenerativeAI(
            model=settings.ROUTER_MODEL_NAME or settings.LLM_MODEL_NAME,
            google_api_key=settings.GOOGLE_API_KEY,
            temperature=settings.ROUTER_TEMPERATURE,
            max_output_tokens=settings.ROUTER_MAX_TOKENS,
        )

    @staticmethod
    def _message_text(message: Any) -> str:
        content = getattr(message, "content", message)
        if isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, dict) and "text" in part:
                    parts.append(part["text"])
                else:
                    parts.append(str(part))
            return "\n".join(parts)
        return str(content)

    @staticmethod
    def _parse_json(text: str) -> dict:
        parsed = JsonOutputParser().parse(text)
        if not isinstance(parsed, dict):
            raise ValueError("Router output must be a JSON object")
        return parsed
