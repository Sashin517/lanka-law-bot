from __future__ import annotations

import re


DRAFTING_KEYWORDS = (
    "draft",
    "prepare",
    "write",
    "generate",
    "format",
    "agreement",
    "contract",
    "pleading",
    "affidavit",
    "notice",
    "letter of demand",
)

REVIEW_KEYWORDS = (
    "review",
    "check this",
    "critique",
    "risky clause",
    "risky clauses",
    "find risks",
    "analyze this document",
    "analyse this document",
)

RESEARCH_KEYWORDS = (
    "leading case",
    "leading cases",
    "precedent",
    "case law",
    "current legal position",
    "comprehensive",
    "research",
    "compare",
)

REASONING_KEYWORDS = (
    "lawful",
    "applicable",
    "apply",
    "liable",
    "liability",
    "enforceable",
    "risk",
    "likely to succeed",
    "interpret",
)

QUICK_QA_KEYWORDS = (
    "section",
    "act",
    "clause",
    "definition",
    "define",
    "penalty",
    "what does",
    "what is",
)


def contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in keywords)


def has_section_reference(text: str) -> bool:
    return bool(re.search(r"\b(section|s\.)\s*\d+[a-z]?(?:\(\w+\))*", text, re.IGNORECASE))


def extract_section_refs(text: str) -> list[str]:
    return re.findall(r"\b(?:section|s\.)\s*\d+[a-z]?(?:\(\w+\))*", text, re.IGNORECASE)


def extract_dates(text: str) -> list[str]:
    return re.findall(r"\b(?:18|19|20)\d{2}\b", text)
