"""Shared helper functions for worker node output parsing.

All worker nodes parse hybrid JSON (metadata + markdown) from the LLM.
These helpers extract common fields, verify citations via the existing
CitationVerifier, and convert data for the agent state.
"""

from __future__ import annotations

import re
import logging

from app.agents.state import SourceChunk
from app.schemas.responses import CitedClaim, LegalResponse, SourceReference
from app.services.generation.citation_verifier import CitationVerifier

logger = logging.getLogger(__name__)

# Matches citation anchors like [LAW-1], [DOC-2], [LAW-12]
_ANCHOR_RE = re.compile(r"\[(?:LAW|DOC)-\d+\]")


def extract_first_paragraph(markdown: str) -> str:
    """Extract the first non-heading paragraph as a plain-text summary.

    Used as a fallback summary for grounding and backward compatibility.
    """
    for line in markdown.split("\n"):
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped[:500]
    return markdown[:500]


def normalize_confidence(value: str) -> str:
    """Clamp confidence to one of the valid enum values."""
    return value if value in {"high", "medium", "low"} else "medium"


def build_and_verify_sources(
    sources_used: list[str],
    citation_map: dict[str, SourceReference],
    verifier: CitationVerifier,
) -> set[str]:
    """Run the existing CitationVerifier on sources_used, return valid IDs.

    Builds a temporary LegalResponse with one CitedClaim per anchor
    so the verifier can strip hallucinated ones in the standard way.
    """
    # Build a LegalResponse with the LLM-claimed anchors as analysis items
    claims = [
        CitedClaim(statement=f"Cited {anchor}", citation_ids=[anchor])
        for anchor in sources_used
    ]
    temp_response = LegalResponse(
        summary="",
        analysis=claims,
        sources=list(citation_map.values()),
        confidence="medium",
    )

    # Run the existing verifier — strips invalid anchors, logs warnings
    verified = verifier.verify(temp_response)

    # Collect the surviving anchor IDs
    valid_ids: set[str] = set()
    for claim in verified.analysis:
        valid_ids.update(claim.citation_ids)

    return valid_ids


def strip_invalid_anchors(markdown: str, valid_ids: set[str]) -> str:
    """Remove hallucinated citation anchors from markdown text.

    Any [LAW-X] or [DOC-X] not in valid_ids is stripped so the user
    never sees a non-existent reference.
    """
    stripped = 0

    def _replace(match: re.Match) -> str:
        nonlocal stripped
        anchor = match.group(0)
        if anchor in valid_ids:
            return anchor
        stripped += 1
        return ""

    cleaned = _ANCHOR_RE.sub(_replace, markdown)

    if stripped > 0:
        logger.info("Stripped %d hallucinated anchors from markdown.", stripped)

    return cleaned


def to_source_chunks(
    citation_map: dict[str, SourceReference],
) -> list[SourceChunk]:
    """Convert the citation map into agent-state SourceChunks."""
    return [
        SourceChunk(
            citation_id=ref.citation_id,
            content=ref.content or ref.excerpt,
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
