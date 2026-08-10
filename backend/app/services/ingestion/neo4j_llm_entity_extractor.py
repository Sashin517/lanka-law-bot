"""
Neo4j LLM Entity Extractor Service.
Uses Google Gemini to extract entities, relationships, concepts, and temporal versioning
metadata from legal markdown text.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from app.core.config import settings

logger = logging.getLogger(__name__)


class LegalConceptExtraction(BaseModel):
    name: str = Field(description="Canonical name of the legal concept (e.g., 'Tenancy Termination', 'Duty of Care').")
    aliases: List[str] = Field(default_factory=list, description="Common alternative names or synonyms.")
    description: str = Field(description="Brief explanation of the legal concept.")


class AmendmentExtraction(BaseModel):
    amending_act: str = Field(description="The short title or citation of the amending Act (e.g., 'Rent (Amendment) Act No. 23 of 2002').")
    amended_act: str = Field(description="The short title or citation of the Act being amended or repealed.")
    sections_affected: List[str] = Field(default_factory=list, description="List of specific sections amended/repealed (e.g., ['4', '14(1)']).")
    type: str = Field(description="The action type. Must be one of: 'amends', 'repeals', 'partially_repeals'.")


class StatuteCitationExtraction(BaseModel):
    section_ref: str = Field(description="The section or clause label cited (e.g., 'Section 4A(1)(b)').")
    act_name: str = Field(description="The canonical name of the statute cited (e.g., 'Evidence Ordinance').")
    context: str = Field(description="How the statute is referenced. Must be one of: 'cited', 'interpreted', 'applied', 'distinguished'.")


class CaseCitationExtraction(BaseModel):
    case_name: str = Field(description="The name of the cited case (e.g., 'Perera v. Silva').")
    citation: Optional[str] = Field(None, description="The legal reporter citation if present (e.g., '[1998] 2 SLR 45').")
    treatment: str = Field(description="How the court treats the cited case. Must be one of: 'followed', 'applied', 'distinguished', 'overruled', 'cited'.")


class DeepLegalExtractionResult(BaseModel):
    legal_concepts: List[LegalConceptExtraction] = Field(default_factory=list)
    amendments: List[AmendmentExtraction] = Field(default_factory=list)
    statute_citations: List[StatuteCitationExtraction] = Field(default_factory=list)
    case_citations: List[CaseCitationExtraction] = Field(default_factory=list)
    is_current: bool = Field(default=True, description="False if this Act/Ordinance is fully repealed or superseded. True otherwise.")
    repealed_by: Optional[str] = Field(None, description="If repealed, the title/number of the Act that repealed it.")


EXTRACTION_PROMPT = """You are a highly experienced Sri Lankan Legal Technology Lead and AI System Engineer.
Your task is to analyze the following Sri Lankan legal document (either an Act/Ordinance or a Case Law Judgment) and perform deep entity-relationship and concept extraction.

Legal documents are complex and full of subtle references. Follow these strict rules during extraction:
1. **Legal Concepts**: Identify the core legal concepts discussed (e.g., 'Burden of Proof', 'Specific Performance', 'Tenant Eviction'). Avoid generic terms. Provide clean, normalized names, alternative names (aliases), and a concise description of how it applies here.
2. **Amendments & Repeals**: For Acts/Ordinances, identify if they amend, repeal, or partially repeal any prior statutes. Note the sections affected.
3. **Statute Citations**: List all sections of other statutes cited. Resolve alphanumeric sections and subsections accurately (e.g., '4A(2)(c)'). Classify whether the section is simply 'cited' or actively 'interpreted' (e.g., its meaning is analyzed or disputed).
4. **Case Citations**: List all prior cases cited. Extract their reporter citations if present, and classify the treatment (e.g., 'followed', 'applied', 'distinguished', 'overruled', or simply 'cited').
5. **Temporal Status**: If this document itself is a repealed Act/Ordinance (indicated by text like 'Repealed by Act No. X' or 'This Act is hereby repealed'), set 'is_current' to false and specify the 'repealed_by' Act.

OUTPUT FORMAT:
Your response must be a valid, parseable JSON object matching the schema below. Do not wrap the JSON in Markdown code block backticks.

JSON Schema:
{json_schema}

Legal Document Text:
{document_text}
"""


class Neo4jLLMEntityExtractor:
    """Service that connects to Gemini to extract rich relationship & concept graph metadata."""

    def __init__(self) -> None:
        self._llm = ChatGoogleGenerativeAI(
            model=settings.LLM_MODEL_NAME,
            google_api_key=settings.GOOGLE_API_KEY,
            temperature=0.0,
            max_output_tokens=settings.LLM_MAX_TOKENS,
        )
        self._parser = JsonOutputParser(pydantic_object=DeepLegalExtractionResult)
        self._prompt = ChatPromptTemplate.from_template(EXTRACTION_PROMPT)
        self._chain = self._prompt | self._llm | self._parser

    def extract(self, document_text: str) -> DeepLegalExtractionResult:
        """Runs the extraction chain on the provided legal markdown text."""
        try:
            # We crop the text if it is excessively long to fit the token context window
            # but preserve enough metadata. Typical Sri Lankan acts are reasonably sized.
            max_chars = 30000
            cropped_text = document_text
            if len(document_text) > max_chars:
                # Keep first 20k and last 10k to catch title/preamble and repeal/final sections
                cropped_text = document_text[:20000] + "\n... [TRUNCATED] ...\n" + document_text[-10000:]

            logger.info("Sending document text (%d chars) to Gemini for deep graph metadata extraction...", len(cropped_text))
            
            schema_json = json.dumps(DeepLegalExtractionResult.model_json_schema(), indent=2)
            raw_result = self._chain.invoke({
                "json_schema": schema_json,
                "document_text": cropped_text
            })

            # Check if parsing was fully successful
            return DeepLegalExtractionResult.model_validate(raw_result)

        except Exception as exc:
            logger.exception("Gemini deep extraction failed: %s", exc)
            # Return empty baseline result so ingestion doesn't crash
            return DeepLegalExtractionResult(
                legal_concepts=[],
                amendments=[],
                statute_citations=[],
                case_citations=[],
                is_current=True,
                repealed_by=None
            )
