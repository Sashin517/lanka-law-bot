from __future__ import annotations

import math

from langchain_core.documents import Document


def retrieval_dedup_key(document: Document) -> str:
    """Return a stable key for deduplicating retrieval results.

    Priority: chunk_id > point_id > citation_id > text_hash > content prefix.

    NOTE: ``parent_id`` is deliberately excluded because multiple distinct
    child chunks share the same parent.  Using it would incorrectly merge
    them during Reciprocal Rank Fusion.
    """
    metadata = document.metadata or {}
    primary = (
        metadata.get("chunk_id")
        or metadata.get("point_id")
        or metadata.get("citation_id")
    )
    if primary:
        return primary
    # Content-based fallback — use a longer window for accuracy
    return metadata.get("text_hash") or document.page_content[:500]


def reciprocal_rank_fusion(
    ranked_lists: list[list[Document]],
    k: int = 60,
    weights: list[float] | None = None,
) -> list[Document]:
    if k <= 0:
        raise ValueError("RRF k must be positive")
    if weights is None:
        weights = [1.0] * len(ranked_lists)
    if len(weights) != len(ranked_lists):
        raise ValueError("weights must contain one value per ranked list")
    if any(not math.isfinite(weight) or weight < 0 for weight in weights):
        raise ValueError("RRF weights must be finite and non-negative")
    if ranked_lists and sum(weights) <= 0:
        raise ValueError("at least one RRF weight must be positive")

    scores: dict[str, float] = {}
    docs_by_key: dict[str, Document] = {}
    channels_by_key: dict[str, dict[str, dict[str, float | int | None]]] = {}

    for list_index, (ranked_list, weight) in enumerate(
        zip(ranked_lists, weights, strict=True)
    ):
        for rank, document in enumerate(ranked_list, start=1):
            key = retrieval_dedup_key(document)
            scores[key] = scores.get(key, 0.0) + weight / (k + rank)
            docs_by_key.setdefault(key, document)
            channel = str(
                document.metadata.get("retrieval_channel") or f"channel_{list_index}"
            )
            channels_by_key.setdefault(key, {})[channel] = {
                "rank": rank,
                "score": document.metadata.get("retrieval_score"),
                "weight": weight,
            }

    ordered: list[Document] = []
    for key, score in sorted(scores.items(), key=lambda item: item[1], reverse=True):
        document = docs_by_key[key]
        document.metadata["rrf_score"] = score
        document.metadata["retrieval_channels"] = channels_by_key[key]
        ordered.append(document)
    return ordered
