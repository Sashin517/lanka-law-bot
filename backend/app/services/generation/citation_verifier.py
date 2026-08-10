from __future__ import annotations

import logging

from app.schemas.responses import CitedClaim, LegalResponse

logger = logging.getLogger(__name__)


def _norm(anchor: str) -> str:
    if not anchor:
        return ""
    a = str(anchor).strip().upper()
    return f"[{a}]" if not a.startswith("[") else a



class CitationVerifier:

    def verify(self, response: LegalResponse) -> LegalResponse:

        # Build the set of valid citation anchors from sources (raw and normalized)
        valid_ids: set[str] = set()
        for src in response.sources:
            if src.citation_id:
                valid_ids.add(src.citation_id)
                valid_ids.add(_norm(src.citation_id))

        verified_count = 0
        stripped_count = 0

        verified_analysis = []
        for claim in response.analysis:
            # Filter to only valid citation references
            valid_citations = []
            invalid_citations = []
            for c in claim.citation_ids:
                if c in valid_ids or _norm(c) in valid_ids:
                    valid_citations.append(c)
                else:
                    invalid_citations.append(c)

            if invalid_citations:
                stripped_count += len(invalid_citations)
                logger.warning(
                    "Stripped hallucinated citations %s from statement: '%s'",
                    invalid_citations,
                    claim.statement[:80],
                )

            if not valid_citations:
                # No valid citations remain — flag the statement
                claim.statement += " [citation unverified]"
                claim.citation_ids = []
            else:
                claim.citation_ids = valid_citations
                verified_count += len(valid_citations)

            verified_analysis.append(claim)

        response.analysis = verified_analysis

        if stripped_count > 0:
            logger.info(
                "Citation verification: %d verified, %d stripped.",
                verified_count,
                stripped_count,
            )

        return response

