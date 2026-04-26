from __future__ import annotations

import logging

from app.schemas.responses import CitedClaim, LegalResponse

logger = logging.getLogger(__name__)


class CitationVerifier:

    def verify(self, response: LegalResponse) -> LegalResponse:

        # Build the set of valid citation anchors from sources
        valid_ids: set[str] = {src.citation_id for src in response.sources}

        verified_count = 0
        stripped_count = 0

        verified_analysis = []
        for claim in response.analysis:
            # Filter to only valid citation references
            valid_citations = [c for c in claim.citation_ids if c in valid_ids]
            invalid_citations = [c for c in claim.citation_ids if c not in valid_ids]

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
