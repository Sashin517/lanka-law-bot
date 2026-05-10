from __future__ import annotations

from langchain_core.documents import Document


def retrieval_dedup_key(document: Document) -> str:
    metadata = document.metadata or {}
    return (
        metadata.get("parent_id")
        or metadata.get("chunk_id")
        or metadata.get("point_id")
        or metadata.get("text_hash")
        or document.page_content[:200]
    )


def reciprocal_rank_fusion(
    ranked_lists: list[list[Document]],
    k: int = 60,
) -> list[Document]:
    scores: dict[str, float] = {}
    docs_by_key: dict[str, Document] = {}

    for ranked_list in ranked_lists:
        for rank, document in enumerate(ranked_list, start=1):
            key = retrieval_dedup_key(document)
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
            docs_by_key.setdefault(key, document)

    return [
        docs_by_key[key]
        for key, _score in sorted(
            scores.items(),
            key=lambda item: item[1],
            reverse=True,
        )
    ]
