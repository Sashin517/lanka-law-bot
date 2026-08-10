"""Shared validation and option handling for pipeline ablation studies."""

from __future__ import annotations

from typing import Any, Mapping


class AblationConfigurationError(ValueError):
    """Raised when a requested ablation cannot be applied as declared."""


RETRIEVAL_ABLATION_KEYS = frozenset(
    {
        "disable_bm25",
        "disable_dense",
        "disable_reranking",
        "expand_parents",
    }
)


def retrieval_search_kwargs(config: Mapping[str, Any] | None) -> dict[str, bool]:
    """Return only retrieval-layer options, with each keyword emitted once.

    Pipeline-only keys such as ``skip_verification`` and ``force_fast_path``
    must never leak into retrieval services. Centralising this conversion also
    prevents ``expand_parents`` from being passed both explicitly and through
    ``**ablation_config``.
    """
    config = config or {}
    return {
        "expand_parents": bool(config.get("expand_parents", True)),
        "disable_bm25": bool(config.get("disable_bm25", False)),
        "disable_dense": bool(config.get("disable_dense", False)),
        "disable_reranking": bool(config.get("disable_reranking", False)),
    }


def validate_retrieval_combination(config: Mapping[str, Any] | None) -> None:
    """Reject contradictory retrieval configurations before doing any I/O."""
    options = retrieval_search_kwargs(config)
    if options["disable_bm25"] and options["disable_dense"]:
        raise AblationConfigurationError(
            "disable_bm25 and disable_dense cannot both be true; "
            "the configuration would disable every primary retriever"
        )


def describe_pinecone_effects(
    config: Mapping[str, Any] | None,
    *,
    bm25_available: bool,
    reranking_available: bool,
) -> dict:
    """Validate and describe a Pinecone ablation without performing I/O."""
    validate_retrieval_combination(config)
    options = retrieval_search_kwargs(config)

    if options["disable_dense"] and not bm25_available:
        raise AblationConfigurationError(
            "sparse_only requires full-text-search fields on the configured "
            "Pinecone document index; dense fallback is disabled for ablation runs"
        )
    if options["disable_bm25"] and not bm25_available:
        raise AblationConfigurationError(
            "dense_only has no effect because BM25 is not configured"
        )
    if options["disable_reranking"] and not reranking_available:
        raise AblationConfigurationError(
            "no_reranking has no effect because reranking is not configured"
        )

    if options["disable_dense"]:
        channels = ["sparse"]
    elif options["disable_bm25"]:
        channels = ["dense"]
    elif bm25_available:
        channels = ["dense", "sparse"]
    else:
        channels = ["dense"]

    return {
        "backend": "pinecone",
        "retrieval_channels": channels,
        "reranking_enabled": (
            not options["disable_reranking"] and reranking_available
        ),
        "parent_expansion_enabled": options["expand_parents"],
        "dense_fallback_allowed": not options["disable_dense"],
    }


def describe_neo4j_effects(config: Mapping[str, Any] | None) -> dict:
    """Validate and describe an effective Neo4j retrieval ablation."""
    validate_retrieval_combination(config)
    options = retrieval_search_kwargs(config)

    if options["disable_dense"]:
        channels = ["sparse"]
    elif options["disable_bm25"]:
        channels = ["dense"]
    else:
        channels = ["dense", "sparse", "graph"]

    return {
        "backend": "neo4j",
        "retrieval_channels": channels,
        "reranking_enabled": not options["disable_reranking"],
        "parent_expansion_enabled": options["expand_parents"],
        "dense_fallback_allowed": False,
    }
