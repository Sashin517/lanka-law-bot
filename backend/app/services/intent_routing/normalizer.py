from __future__ import annotations

import re


_NORMALIZATIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bsec\.\s*", re.IGNORECASE), "section "),
    (re.compile(r"\bs\.\s*", re.IGNORECASE), "section "),
    (re.compile(r"\bart\.\s*", re.IGNORECASE), "article "),
    (re.compile(r"\bvs\.\b", re.IGNORECASE), "v"),
    (re.compile(r"\bvs\b", re.IGNORECASE), "v"),
)


def normalize_query(question: str) -> str:
    normalized = (question or "").strip()
    normalized = re.sub(r"\s+", " ", normalized)
    for pattern, replacement in _NORMALIZATIONS:
        normalized = pattern.sub(replacement, normalized)
    return re.sub(r"\s+", " ", normalized).strip()
